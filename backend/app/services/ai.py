"""AI drafting and summarisation.

Three providers behind one function. Gemini and Azure OpenAI are hosted;
"local" is anything exposing an OpenAI-compatible ``/chat/completions``
endpoint (Ollama, LM Studio, vLLM), which is the option to pick when
tenant names and rent figures should not leave the building.

Two rules hold everywhere in this module:

  * **A draft is never a send.** Everything here returns text for a
    person to read, edit and approve. No function in this file delivers
    anything; the caller decides, and the caller is always a screen with
    a human in front of it.
  * **Failure is not fatal.** If the provider is off, misconfigured or
    unreachable, the caller gets a clear message and falls back to the
    template. A reminder that goes out in plain wording beats one that
    doesn't go out because a model was down.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import settings as settings_service

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class AIError(RuntimeError):
    """Raised for a configuration or provider failure worth showing."""


def is_enabled() -> bool:
    return settings_service.get_bool("ai.enabled", False)


def config() -> dict:
    return {
        "provider": (settings_service.get("ai.provider") or "gemini").strip(),
        "api_key": settings_service.get("ai.api_key") or "",
        "endpoint": (settings_service.get("ai.endpoint") or "").strip().rstrip("/"),
        "model": (settings_service.get("ai.model") or "").strip(),
        "timeout": int(settings_service.get("ai.timeout_seconds") or 30),
    }


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise AIError(f"The AI provider returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AIError(f"Could not reach the AI provider: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise AIError("The AI provider returned something that wasn't JSON.") from exc


def complete(prompt: str, *, system: str | None = None, max_tokens: int = 800) -> str:
    """Ask the configured provider for one completion. Returns plain text."""
    if not is_enabled():
        raise AIError("AI features are switched off (Settings → AI).")
    cfg = config()
    if not cfg["model"]:
        raise AIError("No AI model is configured.")

    provider = cfg["provider"]
    if provider == "gemini":
        return _complete_gemini(cfg, prompt, system, max_tokens)
    if provider == "azure":
        return _complete_azure(cfg, prompt, system, max_tokens)
    if provider == "local":
        return _complete_local(cfg, prompt, system, max_tokens)
    raise AIError(f"Unknown AI provider: {provider!r}")


def _complete_gemini(cfg: dict, prompt: str, system: str | None, max_tokens: int) -> str:
    if not cfg["api_key"]:
        raise AIError("Set the Gemini API key first.")
    url = f"{GEMINI_BASE}/models/{cfg['model']}:generateContent"
    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    data = _post_json(url, payload, {"x-goog-api-key": cfg["api_key"]}, cfg["timeout"])
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("Gemini replied in an unexpected shape.") from exc


def _chat_messages(prompt: str, system: str | None) -> list[dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _read_openai_choice(data: dict) -> str:
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("The provider replied in an unexpected shape.") from exc


def _complete_azure(cfg: dict, prompt: str, system: str | None, max_tokens: int) -> str:
    if not cfg["endpoint"]:
        raise AIError("Set the Azure endpoint first.")
    if not cfg["api_key"]:
        raise AIError("Set the Azure API key first.")
    # `model` is the *deployment* name on Azure, not the base model.
    url = (f"{cfg['endpoint']}/openai/deployments/{cfg['model']}"
           f"/chat/completions?api-version=2024-02-01")
    data = _post_json(
        url,
        {"messages": _chat_messages(prompt, system),
         "max_tokens": max_tokens, "temperature": 0.4},
        {"api-key": cfg["api_key"]}, cfg["timeout"])
    return _read_openai_choice(data)


def _complete_local(cfg: dict, prompt: str, system: str | None, max_tokens: int) -> str:
    if not cfg["endpoint"]:
        raise AIError("Set the local endpoint first (e.g. http://localhost:11434/v1).")
    headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
    data = _post_json(
        f"{cfg['endpoint']}/chat/completions",
        {"model": cfg["model"], "messages": _chat_messages(prompt, system),
         "max_tokens": max_tokens, "temperature": 0.4},
        headers, cfg["timeout"])
    return _read_openai_choice(data)


# ----------------------------------------------------------------------
# What we actually ask it for
# ----------------------------------------------------------------------

HOUSE_STYLE = (
    "You write correspondence for GreenTech Trading & Contracting, a property "
    "letting company in Qatar. Amounts are Qatari Riyals (QAR). Write in plain, "
    "courteous business English — brief, specific, no marketing language and no "
    "exclamation marks. Never invent a figure, a date or a name: use only what "
    "you are given. Sign off as 'GreenTech Trading & Contracting'. "
    "Return only the message body, with no subject line and no preamble."
)


def draft_message(*, purpose: str, facts: dict, tone: str = "courteous") -> str:
    """Draft one message from a dictionary of facts.

    `facts` is rendered verbatim into the prompt so the model has
    nothing to invent — every number it can use is one we handed it.
    """
    lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in facts.items() if v not in (None, ""))
    prompt = (
        f"Write a {tone} email for this purpose: {purpose}.\n\n"
        f"Use exactly these facts and no others:\n{lines}\n\n"
        "Keep it under 150 words."
    )
    return complete(prompt, system=HOUSE_STYLE, max_tokens=500)


def monthly_summary(figures: dict) -> str:
    """The AI monthly summary — a short management note over the numbers
    the P&L and collections pages already computed."""
    lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in figures.items())
    prompt = (
        "Write a short management summary of this month's property-letting "
        "performance for the company's directors.\n\n"
        f"Figures:\n{lines}\n\n"
        "Structure it as: one opening sentence stating the headline result, "
        "then 3-5 bullet points on collection, arrears and margin, then one "
        "sentence naming the single thing most worth attention next month. "
        "State only what the figures support; if something looks poor, say so "
        "plainly. Under 200 words."
    )
    return complete(prompt, system=HOUSE_STYLE, max_tokens=700)


def test_connection() -> str:
    """Round-trip the provider so Settings can prove the key works."""
    reply = complete(
        "Reply with exactly: GreenTech portal AI connection OK",
        system="You are a connectivity check. Reply with exactly what is asked.",
        max_tokens=32,
    )
    if not reply:
        raise AIError("The provider replied with nothing.")
    return reply

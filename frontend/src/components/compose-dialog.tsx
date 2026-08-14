"use client";

import { useEffect, useState } from "react";
import { Sparkles, Send, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { Modal, Field, inputClass, textareaClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

/**
 * Compose an email to a client or landlord.
 *
 * The recipient is never typed — it is resolved on the server from the
 * party, so this screen cannot be used to mail an arbitrary address.
 * The AI button drafts into the body for editing; it never sends, and
 * the operator presses Send themselves.
 */
export function ComposeDialog({
  open, partyType, partyId, partyName, partyEmail, contractId, onClose,
}: {
  open: boolean;
  partyType: "client" | "landlord";
  partyId: number;
  partyName: string;
  partyEmail: string | null;
  contractId?: number;
  onClose: () => void;
}) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [purpose, setPurpose] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (open) { setSubject(""); setBody(""); setPurpose(""); }
  }, [open]);

  const draft = async () => {
    if (!purpose.trim()) {
      toast.error("Say what the message is for", "The AI needs a purpose to write to.");
      return;
    }
    setDrafting(true);
    try {
      const r = await api.post("/messaging/ai/draft", {
        purpose,
        contract_id: contractId ?? null,
        facts: { [`${partyType}_name`]: partyName },
      });
      setBody(r.data?.data?.draft ?? "");
      toast.success("Draft ready", "Read it before sending — it is only a draft.");
    } catch (err: unknown) {
      toast.error("Could not draft that", errorMessage(err));
    } finally { setDrafting(false); }
  };

  const send = async () => {
    if (!confirm(`Send this email to ${partyName} <${partyEmail}>?`)) return;
    setSending(true);
    try {
      const r = await api.post("/messaging/send", {
        party_type: partyType, party_id: partyId, subject, body,
      });
      const status = r.data?.data?.status;
      if (status === "sent") {
        toast.success("Sent", `Delivered to ${partyEmail}`);
      } else {
        toast.success("Logged, not sent", r.data?.message ?? "");
      }
      onClose();
    } catch (err: unknown) {
      toast.error("Send failed", errorMessage(err));
    } finally { setSending(false); }
  };

  const canSend = Boolean(subject.trim() && body.trim() && partyEmail);

  return (
    <Modal open={open} onClose={onClose} title={`Email ${partyName}`} size="lg">
      <div className="space-y-3">
        {!partyEmail ? (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm inline-flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
            <span>
              {partyName} has no email address on file. Add one on their record
              before you can write to them.
            </span>
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-card/40 p-2.5 text-xs">
            To: <span className="font-medium">{partyName}</span>{" "}
            <span className="text-muted-foreground">&lt;{partyEmail}&gt;</span>
          </div>
        )}

        <div className="rounded-lg border border-border bg-card/40 p-3 space-y-2">
          <div className="text-xs font-medium inline-flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-primary" /> Draft with AI
          </div>
          <div className="flex items-center gap-2">
            <input className={inputClass} value={purpose}
              placeholder="e.g. invite them to renew, chase February rent"
              onChange={(e) => setPurpose(e.target.value)} />
            <button type="button" onClick={draft} disabled={drafting}
              className="h-9 shrink-0 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent disabled:opacity-60">
              {drafting ? "Writing…" : "Draft"}
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            The draft uses only the figures already on the record. Read and edit
            it before sending — nothing is sent until you press Send.
          </p>
        </div>

        <Field label="Subject">
          <input className={inputClass} value={subject}
            onChange={(e) => setSubject(e.target.value)} />
        </Field>
        <Field label="Message">
          <textarea className={textareaClass} rows={12} value={body}
            onChange={(e) => setBody(e.target.value)} />
        </Field>

        <div className="flex justify-between gap-2 pt-2 border-t border-border">
          <button type="button" onClick={onClose}
            className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
            Cancel
          </button>
          <button type="button" onClick={send} disabled={!canSend || sending}
            className="h-9 inline-flex items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            <Send className="h-4 w-4" /> {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

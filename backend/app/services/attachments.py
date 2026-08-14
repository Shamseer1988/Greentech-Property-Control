"""Attachment storage with content-aware validation (Phase 3).

The previous implementation only checked the filename extension and
trusted the client-supplied Content-Type header — both attacker-controlled.
We now:
  * sniff the actual bytes with libmagic and require the MIME to match
    the claimed extension's allow-list,
  * enforce a per-type byte cap on top of MAX_CONTENT_LENGTH,
  * strip EXIF from images by re-saving through Pillow,
  * store the *sniffed* MIME (not the client header) on the row,
  * drop SVG entirely — SVG can carry inline script.
"""
import io
import os
import secrets
from datetime import datetime
from typing import BinaryIO

import magic
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
from flask import current_app

from ..extensions import db
from ..models import Attachment

KB = 1024
MB = 1024 * KB

# extension -> {accepted MIME prefixes, hard byte cap}
EXTENSION_RULES: dict[str, dict] = {
    "pdf":  {"mimes": {"application/pdf"}, "max_bytes": 15 * MB},
    "png":  {"mimes": {"image/png"}, "max_bytes": 8 * MB, "image": True},
    "jpg":  {"mimes": {"image/jpeg"}, "max_bytes": 8 * MB, "image": True},
    "jpeg": {"mimes": {"image/jpeg"}, "max_bytes": 8 * MB, "image": True},
    "gif":  {"mimes": {"image/gif"}, "max_bytes": 8 * MB, "image": True},
    "webp": {"mimes": {"image/webp"}, "max_bytes": 8 * MB, "image": True},
    "doc":  {"mimes": {"application/msword",
                       "application/x-ole-storage"}, "max_bytes": 20 * MB},
    "docx": {"mimes": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       "application/zip"}, "max_bytes": 20 * MB},
    "xls":  {"mimes": {"application/vnd.ms-excel",
                       "application/x-ole-storage"}, "max_bytes": 20 * MB},
    "xlsx": {"mimes": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       "application/zip"}, "max_bytes": 20 * MB},
    "csv":  {"mimes": {"text/csv", "text/plain",
                       "application/csv"}, "max_bytes": 5 * MB},
    "txt":  {"mimes": {"text/plain"}, "max_bytes": 1 * MB},
}

ALLOWED_EXTENSIONS = set(EXTENSION_RULES.keys())

# Default response Content-Type for downloads — always
# `application/octet-stream` so a stored `text/html` or stray
# `image/svg+xml` from a legacy row can never render inline. The browser
# already gets `Content-Disposition: attachment` from send_file.
DOWNLOAD_CONTENT_TYPE = "application/octet-stream"


class UploadError(ValueError):
    """Raised by store_file() for any rejected upload — surfaced to the
    HTTP caller as a 400 by routes/attachments.py."""


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def is_allowed(filename: str) -> bool:
    return _extension(filename) in ALLOWED_EXTENSIONS


def _sniff_mime(stream: BinaryIO) -> str:
    """Read up to 4KB from the start of `stream` and rewind."""
    head = stream.read(4 * KB)
    stream.seek(0)
    if not head:
        return ""
    try:
        return magic.from_buffer(head, mime=True) or ""
    except Exception:
        # libmagic missing or DB error — treat as a soft "unknown" so the
        # caller can decide. We err strict: the rules table requires a
        # match, so "unknown" effectively rejects.
        return ""


def _strip_exif_to_bytes(stream: BinaryIO, ext: str) -> bytes:
    """Open the image with Pillow and re-encode without metadata.

    Returns the cleaned bytes. Raises UploadError if Pillow can't parse
    the image (which usually means it isn't actually an image of the
    claimed format, even if libmagic agreed)."""
    stream.seek(0)
    try:
        img = Image.open(stream)
        img.load()  # force a full decode so we surface errors here
    except (UnidentifiedImageError, OSError) as exc:
        raise UploadError(f"Image could not be decoded: {exc}") from exc

    fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
           "gif": "GIF", "webp": "WEBP"}[ext]

    # Convert palette modes that some formats don't support cleanly.
    if fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    out = io.BytesIO()
    save_kwargs: dict = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = 90
        save_kwargs["optimize"] = True
    img.save(out, **save_kwargs)
    return out.getvalue()


def store_file(
    *,
    file: FileStorage,
    entity_type: str,
    entity_id: int | str,
    category: str | None,
    actor_id: int | None,
    remarks: str | None = None,
    doc_number: str | None = None,
    issue_date=None,
    expiry_date=None,
    trusted_source: bool = False,
) -> Attachment:
    """`trusted_source=True` skips the content-sniff (step 1) — for
    bytes the server just generated itself (e.g. a python-docx-built
    agreement), not a user upload. That sniff exists to catch a
    mislabeled/malicious *user* file; it doesn't apply to our own
    trusted library output, and in practice python-docx's zip layout
    isn't always recognised as the specific OOXML wordprocessingml MIME
    by libmagic on every platform (it can fall back to
    `application/octet-stream` even though the bytes are a perfectly
    valid .docx) — confirmed by testing against a real Word-authored
    file, which sniffs correctly, versus a python-docx-generated one,
    which doesn't. The byte-cap and extension checks still apply."""
    if not file or not file.filename:
        raise UploadError("No file provided")

    original = secure_filename(file.filename) or "file"
    ext = _extension(original)
    rule = EXTENSION_RULES.get(ext)
    if rule is None:
        raise UploadError(f"File type '.{ext or '?'}' is not allowed")

    # 1. Sniff the actual content (skipped for our own trusted output —
    # the caller's own declared content_type is trustworthy there since
    # nothing about the bytes came from outside the server).
    if trusted_source:
        sniffed = file.content_type or next(iter(rule["mimes"]))
    else:
        sniffed = _sniff_mime(file.stream)
        if sniffed not in rule["mimes"]:
            raise UploadError(
                f"Content does not match extension '.{ext}' "
                f"(sniffed '{sniffed or 'unknown'}', expected one of "
                f"{sorted(rule['mimes'])})"
            )

    # 2. Per-type byte cap. We re-read to count without loading the whole
    # file twice on disk: tell()-after-seek-end is cheap on FileStorage.
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > rule["max_bytes"]:
        raise UploadError(
            f"File exceeds the {rule['max_bytes'] // MB}MB cap for .{ext}"
        )

    # 3. For images, re-encode without EXIF/metadata. For everything else
    # we keep the bytes as-is.
    if rule.get("image"):
        cleaned = _strip_exif_to_bytes(file.stream, ext)
    else:
        cleaned = file.stream.read()

    # 4. Persist with a random stored name; original is kept on the row
    # only for the download dialog.
    base_folder = current_app.config["UPLOAD_FOLDER"]
    sub = os.path.join(entity_type, str(entity_id), datetime.utcnow().strftime("%Y%m"))
    target_dir = os.path.join(base_folder, sub)
    os.makedirs(target_dir, exist_ok=True)

    stored_name = f"{secrets.token_hex(8)}-{int(datetime.utcnow().timestamp())}.{ext}"
    full_path = os.path.join(target_dir, stored_name)
    with open(full_path, "wb") as out:
        out.write(cleaned)
    final_size = os.path.getsize(full_path)

    att = Attachment(
        entity_type=entity_type,
        entity_id=str(entity_id),
        category=category,
        original_name=original,
        stored_name=stored_name,
        mime_type=sniffed,  # trust the sniff, never the client header
        size_bytes=final_size,
        path=os.path.join(sub, stored_name).replace(os.sep, "/"),
        doc_number=doc_number,
        issue_date=issue_date,
        expiry_date=expiry_date,
        remarks=remarks,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.session.add(att)
    db.session.flush()
    return att


def absolute_path(attachment: Attachment) -> str:
    return os.path.join(current_app.config["UPLOAD_FOLDER"], attachment.path)


def delete_file(attachment: Attachment) -> None:
    try:
        os.remove(absolute_path(attachment))
    except OSError:
        pass
    db.session.delete(attachment)


def company_logo_path() -> str | None:
    """Local file path of the current company logo, or None if there
    isn't one / the file is missing — used by agreement_documents.py to
    embed the logo in a generated .docx header. Mirrors the lookup in
    routes/settings.py::_logo_attachment()."""
    att = (
        Attachment.query
        .filter_by(entity_type="company_logo", entity_id="current")
        .order_by(Attachment.id.desc())
        .first()
    )
    if att is None:
        return None
    path = absolute_path(att)
    return path if os.path.exists(path) else None

"use client";

import { useEffect, useRef, useState } from "react";
import { Upload, Download, Trash2, AlertTriangle, Eye } from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { Modal, Field, inputClass, selectClass } from "@/components/ui/dialog";
import { toast, errorMessage } from "@/components/ui/toast";

type Attachment = {
  id: number;
  category: string | null;
  original_name: string;
  size_bytes: number;
  mime_type: string | null;
  doc_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  created_at: string;
  also_on?: { entity_type: string; code: string; name: string }[];
};

const CATEGORIES: { value: string; label: string }[] = [
  { value: "agreement", label: "Agreement" },
  { value: "company_doc", label: "Company doc (CR)" },
  { value: "govt_doc", label: "Government doc (QID / title deed)" },
  { value: "cheque_copy", label: "Cheque copy" },
  { value: "receipt_voucher", label: "Receipt voucher" },
  { value: "payment_voucher", label: "Payment voucher" },
  { value: "photo", label: "Photo" },
  { value: "other", label: "Other" },
];

// Only these categories are watched by the document-expiry alerts, so
// only these prompt for an expiry date.
const EXPIRING = new Set(["company_doc", "govt_doc"]);

const ALSO_ON_LABEL: Record<string, string> = {
  property: "Property",
  client_contract: "Contract",
  property_agreement: "Agreement",
};

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000);
}

export function AttachmentsTab({ entityType, entityId }: {
  entityType: string;
  entityId: number | string;
}) {
  const [rows, setRows] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [preview, setPreview] = useState<{ att: Attachment; url: string } | null>(null);
  const [previewLoading, setPreviewLoading] = useState<number | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get("/attachments", {
        params: { entity_type: entityType, entity_id: entityId },
      });
      setRows(Array.isArray(resp.data?.data) ? resp.data.data : []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [entityType, entityId]);  // eslint-disable-line react-hooks/exhaustive-deps

  const download = async (att: Attachment) => {
    const resp = await api.get(`/attachments/${att.id}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(resp.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = att.original_name;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isPreviewable = (mime: string | null) =>
    !!mime && (mime.startsWith("image/") || mime === "application/pdf");

  const view = async (att: Attachment) => {
    setPreviewLoading(att.id);
    try {
      const resp = await api.get(`/attachments/${att.id}/download`, { responseType: "blob" });
      const blob = isPreviewable(att.mime_type)
        ? new Blob([resp.data], { type: att.mime_type ?? undefined })
        : resp.data;
      const url = URL.createObjectURL(blob);
      previewUrlRef.current = url;
      setPreview({ att, url });
    } catch (err: unknown) {
      toast.error("Could not open preview", errorMessage(err));
    } finally {
      setPreviewLoading(null);
    }
  };

  const closePreview = () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
    setPreview(null);
  };

  const remove = async (att: Attachment) => {
    if (!confirm(`Delete ${att.original_name}?`)) return;
    try {
      await api.delete(`/attachments/${att.id}`);
      await load();
    } catch (err: unknown) {
      toast.error("Delete failed", errorMessage(err));
    }
  };

  return (
    <div className="space-y-4">
      <Can perm="attachment.upload">
        <div className="glass rounded-xl p-4 flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => setShowUpload(true)}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Upload className="h-4 w-4" /> Upload document
          </button>
          <span className="text-xs text-muted-foreground">
            CR and government documents can carry an expiry date — those feed the renewal alerts.
          </span>
        </div>
      </Can>

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground border-b border-border">
            <tr>
              <th className="py-2 px-3">File</th>
              <th className="py-2 px-3">Category</th>
              <th className="py-2 px-3">Doc no.</th>
              <th className="py-2 px-3">Expiry</th>
              <th className="py-2 px-3">Size</th>
              <th className="py-2 px-3">Uploaded</th>
              <th className="py-2 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="py-10 text-center text-muted-foreground">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={7} className="py-10 text-center text-muted-foreground">No attachments yet</td></tr>
            ) : (
              rows.map((a) => {
                const days = daysUntil(a.expiry_date);
                const warn = days !== null && days <= 60;
                return (
                  <tr key={a.id} className="border-b border-border/60">
                    <td className="py-2 px-3">
                      {a.original_name}
                      {a.also_on && a.also_on.length > 0 && (
                        <div className="text-[11px] text-muted-foreground">
                          Also on: {a.also_on.map((l) => `${ALSO_ON_LABEL[l.entity_type] ?? l.entity_type} ${l.code}`).join(", ")}
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-3 text-muted-foreground">
                      {CATEGORIES.find((c) => c.value === a.category)?.label ?? a.category ?? "—"}
                    </td>
                    <td className="py-2 px-3 font-mono text-xs">{a.doc_number ?? "—"}</td>
                    <td className="py-2 px-3">
                      {a.expiry_date ? (
                        <span className={"text-xs inline-flex items-center gap-1 " + (warn ? "text-amber-600" : "")}>
                          {warn && <AlertTriangle className="h-3 w-3" />}
                          <span className="font-mono">{a.expiry_date}</span>
                          {days !== null && (
                            <span className="text-muted-foreground">
                              ({days < 0 ? `${Math.abs(days)}d ago` : `${days}d`})
                            </span>
                          )}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="py-2 px-3 text-xs">{(a.size_bytes / 1024).toFixed(1)} KB</td>
                    <td className="py-2 px-3 font-mono text-xs">
                      {a.created_at.slice(0, 19).replace("T", " ")}
                    </td>
                    <td className="py-2 px-3 text-right whitespace-nowrap">
                      {isPreviewable(a.mime_type) && (
                        <button
                          onClick={() => view(a)}
                          disabled={previewLoading === a.id}
                          className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent inline-block disabled:opacity-50"
                          aria-label={`View ${a.original_name}`}
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => download(a)}
                        className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent inline-block"
                        aria-label={`Download ${a.original_name}`}
                      >
                        <Download className="h-3.5 w-3.5" />
                      </button>
                      <Can perm="attachment.upload">
                        <button
                          onClick={() => remove(a)}
                          className="h-8 w-8 grid place-items-center rounded-md hover:bg-destructive/10 text-destructive inline-block"
                          aria-label={`Delete ${a.original_name}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </Can>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <UploadDialog
        open={showUpload}
        entityType={entityType}
        entityId={entityId}
        onClose={() => setShowUpload(false)}
        onUploaded={async () => { setShowUpload(false); await load(); }}
      />

      <Modal open={Boolean(preview)} onClose={closePreview}
        title={preview?.att.original_name ?? "Preview"} size="xl">
        {preview && (
          <div className="space-y-3">
            {preview.att.mime_type?.startsWith("image/") ? (
              <img src={preview.url} alt={preview.att.original_name}
                className="max-w-full max-h-[70vh] mx-auto rounded-lg border border-border" />
            ) : preview.att.mime_type === "application/pdf" ? (
              <iframe src={preview.url} title={preview.att.original_name}
                className="w-full h-[70vh] rounded-lg border border-border" />
            ) : (
              <div className="py-10 text-center text-sm text-muted-foreground">
                Preview isn&apos;t available for this file type.
              </div>
            )}
            <div className="flex justify-end">
              <button onClick={() => download(preview.att)}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
                <Download className="h-4 w-4" /> Download
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

type LinkOption = { id: number; label: string };

/** Which second home (if any) a document uploaded on this entity type
 *  can also be tagged to, and how to fetch the choices. Landlord docs
 *  tag to one of the landlord's properties; client docs tag to one of
 *  the client's contracts. (Once landlord contracts exist, a
 *  `landlord: { linkEntityType: "landlord_contract", ... }` entry slots
 *  in the same way.) */
const LINK_CONFIG: Record<string, {
  linkEntityType: string;
  label: string;
  hint: string;
  fetchOptions: (entityId: number | string) => Promise<LinkOption[]>;
}> = {
  landlord: {
    linkEntityType: "property",
    label: "Also show on property (optional)",
    hint: "Tags this same file onto that property's documents too — no second upload.",
    fetchOptions: async (entityId) => {
      const r = await api.get("/properties", { params: { landlord_id: entityId } });
      const rows = Array.isArray(r.data?.data) ? r.data.data : [];
      return rows.map((p: { id: number; code: string; name: string }) => ({ id: p.id, label: `${p.name} (${p.code})` }));
    },
  },
  client: {
    linkEntityType: "client_contract",
    label: "Also show on contract (optional)",
    hint: "Tags this same file onto that contract's documents too — no second upload.",
    fetchOptions: async (entityId) => {
      const r = await api.get("/contracts", { params: { client_id: entityId } });
      const rows = Array.isArray(r.data?.data) ? r.data.data : [];
      return rows.map((c: { id: number; contract_number: string; property?: { name: string } }) =>
        ({ id: c.id, label: `${c.contract_number}${c.property ? ` — ${c.property.name}` : ""}` }));
    },
  },
};

function UploadDialog({ open, entityType, entityId, onClose, onUploaded }: {
  open: boolean;
  entityType: string;
  entityId: number | string;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("agreement");
  const [docNumber, setDocNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [linkEntityId, setLinkEntityId] = useState("");
  const [linkOptions, setLinkOptions] = useState<LinkOption[]>([]);
  const [busy, setBusy] = useState(false);

  const linkConfig = LINK_CONFIG[entityType];

  useEffect(() => {
    if (open) {
      setFile(null);
      setCategory("agreement");
      setDocNumber("");
      setIssueDate("");
      setExpiryDate("");
      setLinkEntityId("");
      if (linkConfig) {
        linkConfig.fetchOptions(entityId).then(setLinkOptions).catch(() => setLinkOptions([]));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("entity_type", entityType);
      fd.append("entity_id", String(entityId));
      fd.append("category", category);
      if (docNumber) fd.append("doc_number", docNumber);
      if (issueDate) fd.append("issue_date", issueDate);
      if (expiryDate) fd.append("expiry_date", expiryDate);
      if (linkConfig && linkEntityId) {
        fd.append("link_entity_type", linkConfig.linkEntityType);
        fd.append("link_entity_id", linkEntityId);
      }
      // No Content-Type header — axios sets multipart/form-data WITH the
      // boundary when it sees FormData. Overriding it drops the boundary
      // and the upload silently fails.
      await api.post("/attachments", fd);
      toast.success("Document uploaded");
      onUploaded();
    } catch (err: unknown) {
      toast.error("Upload failed", errorMessage(err));
    } finally { setBusy(false); }
  };

  const tracksExpiry = EXPIRING.has(category);

  return (
    <Modal open={open} onClose={onClose} title="Upload document">
      <form onSubmit={submit} className="space-y-3">
        <Field label="File">
          <input
            required
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.doc,.docx,.xls,.xlsx,.csv,.txt"
            className={inputClass + " file:mr-3 file:rounded file:border-0 file:bg-accent file:px-2 file:py-1 file:text-xs"}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>
        <Field label="Category">
          <select className={selectClass} value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </Field>
        {linkConfig && (
          <Field label={linkConfig.label}>
            <select className={selectClass} value={linkEntityId} onChange={(e) => setLinkEntityId(e.target.value)}>
              <option value="">— None —</option>
              {linkOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            <div className="text-[11px] text-muted-foreground mt-1">{linkConfig.hint}</div>
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Document number">
            <input className={inputClass} value={docNumber} onChange={(e) => setDocNumber(e.target.value)}
              placeholder="Optional" />
          </Field>
          <Field label="Issue date">
            <input type="date" className={inputClass} value={issueDate}
              onChange={(e) => setIssueDate(e.target.value)} />
          </Field>
        </div>
        <Field label={tracksExpiry ? "Expiry date (feeds renewal alerts)" : "Expiry date"}>
          <input type="date" className={inputClass} value={expiryDate}
            onChange={(e) => setExpiryDate(e.target.value)} />
          {!tracksExpiry && (
            <div className="text-[11px] text-muted-foreground mt-1">
              Only company and government documents are watched by the expiry alerts.
            </div>
          )}
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
            Cancel
          </button>
          <button type="submit" disabled={busy || !file}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

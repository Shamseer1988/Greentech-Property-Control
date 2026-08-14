"use client";

import { useEffect, useRef, useState } from "react";
import {
  Download, Upload, Trash2, RotateCcw, PlayCircle, RefreshCw,
  HardDrive, AlertTriangle, Clock,
} from "lucide-react";
import { api } from "@/lib/api";
import { Can } from "@/components/can";
import { toast, errorMessage } from "@/components/ui/toast";

type BackupFile = {
  filename: string;
  size_bytes: number;
  size_human: string;
  created_at: string;
  kind: "full" | "database";
  attachments: number | null;
};

type BackupInfo = {
  folder: string;
  writable: boolean;
  free_bytes: number | null;
  total_bytes: number | null;
};

function humanBytes(n: number | null): string {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
}

export function BackupPanel() {
  const [files, setFiles] = useState<BackupFile[]>([]);
  const [info, setInfo] = useState<BackupInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null); // which action is running
  const [confirmRestore, setConfirmRestore] = useState<string | null>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [listR, infoR] = await Promise.all([
        api.get("/backups"),
        api.get("/backups/info"),
      ]);
      setFiles(listR.data?.data ?? []);
      setInfo(infoR.data?.data ?? null);
    } catch (err: unknown) {
      toast.error("Could not load backups", errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const runBackupNow = async () => {
    setBusy("create");
    try {
      const r = await api.post("/backups");
      const f = r.data?.data;
      toast.success("Backup created", f?.filename ?? "");
      await load();
    } catch (err: unknown) {
      toast.error("Backup failed", errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const download = async (filename: string) => {
    setBusy(`download:${filename}`);
    try {
      const r = await api.get(`/backups/${encodeURIComponent(filename)}/download`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      toast.error("Download failed", errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (filename: string) => {
    if (!confirm(`Delete backup ${filename}? This cannot be undone.`)) return;
    setBusy(`delete:${filename}`);
    try {
      await api.delete(`/backups/${encodeURIComponent(filename)}`);
      toast.success("Backup deleted", filename);
      await load();
    } catch (err: unknown) {
      toast.error("Delete failed", errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const restoreOnDisk = async (filename: string) => {
    setBusy(`restore:${filename}`);
    try {
      // 10-minute ceiling so the UI never appears frozen indefinitely
      // — pg_restore on a fresh dev DB finishes in seconds, but a
      // multi-GB restore could legitimately run for a few minutes.
      const r = await api.post(
        `/backups/${encodeURIComponent(filename)}/restore`,
        undefined,
        { timeout: 600_000 },
      );
      toast.success("Restore complete", r.data?.message ?? filename);
      setConfirmRestore(null);
      await load();
    } catch (err: unknown) {
      toast.error("Restore failed", errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const uploadAndRestore = async (file: File) => {
    const isFull = file.name.endsWith(".zip");
    if (!isFull && !file.name.endsWith(".dump")) {
      toast.error(
        "Wrong file type",
        "Restore takes a .zip full backup, or a .dump for the database alone.",
      );
      return;
    }
    if (!confirm(
      `Restore from uploaded "${file.name}"?\n\n` +
      "This OVERWRITES the live database with the contents of the file. " +
      (isFull
        ? "Uploaded files are replaced too; the current ones are kept in a dated folder. "
        : "This is a database-only file, so attachments will NOT be restored and " +
          "existing documents will no longer open. ") +
      "Take a backup first if you want to be able to roll back.",
    )) return;

    setBusy("upload");
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.post("/backups/upload-restore", form, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600_000,
      });
      toast.success("Restore complete", r.data?.message ?? file.name);
      await load();
    } catch (err: unknown) {
      toast.error("Restore failed", errorMessage(err));
    } finally {
      setBusy(null);
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    }
  };

  return (
    <Can perm="backup.manage" fallback={
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm">
        You don&apos;t have permission to manage backups. Ask an operator with{" "}
        <span className="font-mono">backup.manage</span>.
      </div>
    }>
      <div className="space-y-4 pt-4 border-t border-border/60">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h3 className="text-base font-semibold inline-flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-primary" /> Backup files
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Database and uploaded documents, zipped together, in{" "}
              <span className="font-mono">{info?.folder ?? "../backups"}</span>.
              The scheduled backup runs based on the setting above.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              className="h-9 inline-flex items-center gap-1.5 rounded-md border border-border bg-card/60 px-3 text-xs hover:bg-accent"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </button>
            <input
              ref={uploadInputRef}
              type="file"
              accept=".zip,.dump"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void uploadAndRestore(f);
              }}
            />
            <button
              onClick={() => uploadInputRef.current?.click()}
              disabled={busy !== null}
              className="h-9 inline-flex items-center gap-1.5 rounded-md border border-border bg-card/60 px-3 text-sm font-medium hover:bg-accent disabled:opacity-60"
            >
              <Upload className="h-4 w-4" />
              {busy === "upload" ? "Restoring…" : "Upload + restore"}
            </button>
            <button
              onClick={runBackupNow}
              disabled={busy !== null}
              className="h-9 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              <PlayCircle className="h-4 w-4" />
              {busy === "create" ? "Backing up…" : "Backup now"}
            </button>
          </div>
        </div>

        {info && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <Stat label="Folder" value={info.folder} mono />
            <Stat label="Writable" value={info.writable ? "yes" : "NO"} tone={info.writable ? "ok" : "bad"} />
            <Stat label="Free space" value={humanBytes(info.free_bytes)} />
            <Stat label="Backup count" value={files.length.toString()} />
          </div>
        )}

        {!info?.writable && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-3 text-sm flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-rose-600 mt-0.5 shrink-0" />
            <div>
              Backup folder isn&apos;t writable by the backend process. Check the
              path set in <span className="font-mono">backup.folder</span> (above) or the
              <span className="font-mono"> BACKUP_FOLDER</span> env var, and the folder permissions.
            </div>
          </div>
        )}

        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-card/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="text-left px-3 py-2 font-medium">File</th>
                <th className="text-left px-3 py-2 font-medium">Contents</th>
                <th className="text-left px-3 py-2 font-medium">Created</th>
                <th className="text-right px-3 py-2 font-medium">Size</th>
                <th className="text-right px-3 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-muted-foreground text-xs animate-pulse">Loading…</td></tr>
              ) : files.length === 0 ? (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-muted-foreground text-xs">
                  No backups yet. Click <span className="font-medium">Backup now</span> to create one.
                </td></tr>
              ) : files.map((f) => (
                <tr key={f.filename} className="border-t border-border/60 hover:bg-accent/30">
                  <td className="px-3 py-2 font-mono text-xs">{f.filename}</td>
                  <td className="px-3 py-2 text-xs">
                    {f.kind === "full" ? (
                      <span className="text-emerald-600">
                        Database + {f.attachments ?? 0} file{f.attachments === 1 ? "" : "s"}
                      </span>
                    ) : (
                      <span className="text-amber-600">Database only</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {new Date(f.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right text-xs">{f.size_human}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => download(f.filename)}
                        disabled={busy !== null}
                        className="h-7 inline-flex items-center gap-1 rounded border border-border bg-card/60 px-2 text-xs hover:bg-accent disabled:opacity-60"
                      >
                        <Download className="h-3 w-3" /> Download
                      </button>
                      <button
                        onClick={() => setConfirmRestore(f.filename)}
                        disabled={busy !== null}
                        className="h-7 inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300 px-2 text-xs hover:bg-amber-500/10 disabled:opacity-60"
                      >
                        <RotateCcw className="h-3 w-3" /> Restore
                      </button>
                      <button
                        onClick={() => remove(f.filename)}
                        disabled={busy !== null}
                        className="h-7 inline-flex items-center gap-1 rounded border border-rose-500/40 bg-rose-500/5 text-rose-700 dark:text-rose-300 px-2 text-xs hover:bg-rose-500/10 disabled:opacity-60"
                      >
                        <Trash2 className="h-3 w-3" /> Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Restore confirmation */}
        {confirmRestore && (
          <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm grid place-items-center p-4">
            <div className="bg-card rounded-xl border border-border shadow-xl max-w-md w-full p-5 space-y-3">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 grid place-items-center rounded-full bg-rose-500/10 text-rose-600 shrink-0">
                  <AlertTriangle className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-semibold">Restore from backup?</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    This will <span className="font-medium">overwrite the entire database</span>{" "}
                    with the contents of <span className="font-mono">{confirmRestore}</span>.
                    Connected users may need to sign in again afterwards.
                  </p>
                  {files.find((f) => f.filename === confirmRestore)?.kind === "database" ? (
                    <p className="text-sm text-amber-600 mt-2">
                      This file holds the database only. Uploaded documents will not be
                      restored, and attachments in the restored data will no longer open.
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground mt-2">
                      Uploaded documents are replaced too. The current ones are moved to a
                      dated folder beside the uploads directory, not deleted.
                    </p>
                  )}
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setConfirmRestore(null)}
                  disabled={busy !== null}
                  className="h-9 rounded-md border border-border bg-card/60 px-4 text-sm hover:bg-accent disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  onClick={() => restoreOnDisk(confirmRestore)}
                  disabled={busy !== null}
                  className="h-9 rounded-md bg-rose-600 px-4 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-60 inline-flex items-center gap-1.5"
                >
                  <RotateCcw className="h-4 w-4" />
                  {busy?.startsWith("restore:") ? "Restoring…" : "Yes, restore"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Can>
  );
}

function Stat({
  label, value, mono, tone,
}: { label: string; value: string; mono?: boolean; tone?: "ok" | "bad" }) {
  const toneCls =
    tone === "ok"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "bad"
      ? "text-rose-600 dark:text-rose-400"
      : "";
  return (
    <div className="rounded-lg border border-border bg-card/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={"text-sm font-medium truncate " + (mono ? "font-mono " : "") + toneCls}>{value}</div>
    </div>
  );
}

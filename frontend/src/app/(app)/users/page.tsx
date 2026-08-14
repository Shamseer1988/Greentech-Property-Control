"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Plus, Pencil, ShieldCheck, UserX, Shield } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth, type Role } from "@/lib/auth-store";
import { Can } from "@/components/can";
import { toast, errorMessage } from "@/components/ui/toast";
import { keys } from "@/lib/query-keys";

type UserRow = {
  id: number;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_super_user: boolean;
  roles: Role[];
};

export default function UsersPage() {
  const has = useAuth((s) => s.has);
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);

  const canView = has("user.view");
  const listQuery = useQuery({
    queryKey: [...keys.users.list(), { q, showInactive }],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (q) params.q = q;
      if (!showInactive) params.status = "active";
      const [u, r] = await Promise.all([
        api.get("/users", { params }),
        api.get("/roles"),
      ]);
      return { rows: u.data.data as UserRow[], roles: r.data.data as Role[] };
    },
    enabled: canView,
  });
  const rows = listQuery.data?.rows ?? [];
  const roles = listQuery.data?.roles ?? [];
  const loading = listQuery.isLoading;
  const load = () => listQuery.refetch();
  const invalidate = () => qc.invalidateQueries({ queryKey: keys.users.all() });

  const deactivate = async (u: UserRow) => {
    if (!confirm(`Deactivate ${u.username}?`)) return;
    await api.delete(`/users/${u.id}`);
    invalidate();
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">Users & Roles</h1>
          <p className="text-sm text-muted-foreground">Manage portal users and their role assignments.</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/users/roles"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent"
          >
            <Shield className="h-4 w-4" /> Roles & Permissions
          </Link>
          <Can perm="user.manage">
            <button
              onClick={() => {
                setEditing(null);
                setShowForm(true);
              }}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" /> New user
            </button>
          </Can>
        </div>
      </div>

      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Search by name, username, or email…"
            className="h-9 w-full max-w-sm rounded-md border border-input bg-card/60 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground shrink-0 whitespace-nowrap">
            <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
            Show deactivated
          </label>
          <button onClick={load} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm hover:bg-accent">
            Search
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground border-b border-border">
              <tr>
                <th className="py-2 pr-4">Username</th>
                <th className="py-2 pr-4">Full name</th>
                <th className="py-2 pr-4">Email</th>
                <th className="py-2 pr-4">Roles</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-muted-foreground">
                    Loading…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-muted-foreground">
                    No users found
                  </td>
                </tr>
              ) : (
                rows.map((u) => (
                  <tr key={u.id} className="border-b border-border/60 hover:bg-accent/30">
                    <td className="py-2 pr-4 font-medium">
                      <div className="flex items-center gap-1.5">
                        {u.username}
                        {u.is_super_user && <ShieldCheck className="h-3.5 w-3.5 text-primary" />}
                      </div>
                    </td>
                    <td className="py-2 pr-4">{u.full_name}</td>
                    <td className="py-2 pr-4 text-muted-foreground">{u.email}</td>
                    <td className="py-2 pr-4">
                      <div className="flex flex-wrap gap-1">
                        {u.roles.map((r) => (
                          <span
                            key={r.id}
                            className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary"
                          >
                            {r.name}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className={
                          "inline-flex items-center rounded-full px-2 py-0.5 text-xs " +
                          (u.is_active
                            ? "bg-emerald-500/10 text-emerald-600"
                            : "bg-muted text-muted-foreground")
                        }
                      >
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-right">
                      <Can perm="user.manage">
                        <div className="inline-flex gap-1">
                          <button
                            onClick={() => {
                              setEditing(u);
                              setShowForm(true);
                            }}
                            className="h-8 w-8 grid place-items-center rounded-md hover:bg-accent"
                            aria-label="Edit"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          {!u.is_super_user && u.is_active && (
                            <button
                              onClick={() => deactivate(u)}
                              className="h-8 w-8 grid place-items-center rounded-md hover:bg-destructive/10 text-destructive"
                              aria-label="Deactivate"
                            >
                              <UserX className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </Can>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showForm && (
        <UserFormDialog
          user={editing}
          roles={roles}
          onClose={() => setShowForm(false)}
          onSaved={async () => {
            setShowForm(false);
            await load();
          }}
        />
      )}
    </div>
  );
}

function UserFormDialog({
  user,
  roles,
  onClose,
  onSaved,
}: {
  user: UserRow | null;
  roles: Role[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [username, setUsername] = useState(user?.username ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [password, setPassword] = useState("");
  const [roleIds, setRoleIds] = useState<number[]>(user?.roles.map((r) => r.id) ?? []);
  const [isActive, setIsActive] = useState(user?.is_active ?? true);
  const [busy, setBusy] = useState(false);

  const toggleRole = (id: number) =>
    setRoleIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (user) {
        await api.put(`/users/${user.id}`, {
          email,
          full_name: fullName,
          is_active: isActive,
          role_ids: roleIds,
          ...(password ? { password } : {}),
        });
        toast.success(`User ${user.username} updated`);
      } else {
        await api.post("/users", {
          username,
          email,
          full_name: fullName,
          password,
          role_ids: roleIds,
          is_active: isActive,
        });
        toast.success(`User ${username} created`);
      }
      onSaved();
    } catch (err: unknown) {
      toast.error("Save failed", errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="glass-strong w-full max-w-lg rounded-2xl p-6">
        <h2 className="text-lg font-semibold mb-4">{user ? "Edit user" : "New user"}</h2>
        <form className="space-y-3" onSubmit={save}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Username">
              <input
                disabled={!!user}
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Full name">
              <input required value={fullName} onChange={(e) => setFullName(e.target.value)} className="input" />
            </Field>
          </div>
          <Field label="Email">
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
            />
          </Field>
          <Field label={user ? "New password (leave blank to keep)" : "Password"}>
            <input
              type="password"
              required={!user}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              minLength={user ? 0 : 8}
            />
          </Field>

          <div>
            <div className="text-sm font-medium mb-1">Roles</div>
            <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto rounded-md border border-border bg-card/40 p-2">
              {roles.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={roleIds.includes(r.id)}
                    onChange={() => toggleRole(r.id)}
                  />
                  {r.name}
                </label>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            Active
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-card/60 px-3 text-sm">
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
      <style jsx>{`
        .input {
          width: 100%;
          height: 2.25rem;
          border-radius: 0.375rem;
          border: 1px solid hsl(var(--input));
          background: hsl(var(--card) / 0.6);
          padding: 0 0.75rem;
          font-size: 0.875rem;
        }
        .input:focus {
          outline: none;
          box-shadow: 0 0 0 2px hsl(var(--ring));
        }
      `}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium">{label}</label>
      {children}
    </div>
  );
}

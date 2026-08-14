# Deployment — GreenTech Real Estate Control Portal

The portal is two processes plus a database:

| Process | What it is | Port |
|---|---|---|
| **Backend** | Flask API served by waitress | 5000 |
| **Frontend** | Next.js production server | 3000 |
| **PostgreSQL** | System of record | 5432 |
| *Celery worker + beat* | *Scheduled expiry sweeps and reminder emails — **only needed from Phase 7***, and only with Redis | — |

Windows is the primary target (the office host). Linux systemd units ship in `deploy/systemd/` for a server deployment.

---

## Prerequisites

- **PostgreSQL 14+** — official installer. Remember the superuser password.
- **Python 3.11** — install with *Add to PATH* checked.
- **Node 20 LTS**.
- **Redis** — *optional*. Memurai on Windows, or `redis-server` on Linux. Without it the rate limiter uses an in-memory store and the Celery processes are skipped. Required only when scheduled reminders go live.

---

## First install (Windows)

```powershell
# 1. Dependencies + frontend build
.\scripts\install-windows.ps1

# 2. Database + schema + seed (roles, permissions, admin, settings)
.\scripts\bootstrap-db.ps1

# 3. Run
.\scripts\start-all.ps1
```

Before step 2, create the database and role, and copy `backend\.env.example` to `backend\.env` with matching values:

```sql
CREATE ROLE greentech LOGIN PASSWORD '<choose-one>';
CREATE DATABASE greentech_realestate OWNER greentech ENCODING 'UTF8';
```

`backend\.env` must set at minimum:

```ini
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
JWT_SECRET_KEY=<a second, different one>
POSTGRES_DB=greentech_realestate
POSTGRES_USER=greentech
POSTGRES_PASSWORD=<the password above>
POSTGRES_HOST=127.0.0.1
SUPERUSER_PASSWORD=<first admin login>
```

Open **http://localhost:3000** and sign in as `admin`.

## Stopping

```powershell
.\scripts\stop-all.ps1
```

It only stops processes running out of this repo, so other apps on the same host are untouched.

---

## Production checklist

The backend **refuses to start** in production with dev secrets or wildcard CORS — that guard is deliberate. Before going live:

- [ ] `FLASK_ENV=production` in `backend\.env`
- [ ] `SECRET_KEY` and `JWT_SECRET_KEY` regenerated (32+ bytes each, different from each other)
- [ ] `CORS_ORIGINS` set to the explicit frontend origin — never `*`
- [ ] `JWT_COOKIE_SECURE=true` (requires HTTPS; cookies are dropped over plain HTTP with this on)
- [ ] `SUPERUSER_PASSWORD` changed from the install value, and the admin password rotated after first login
- [ ] `BACKUP_FOLDER` pointing at a real, writable path — and a restore rehearsed at least once, on a copy, before you need it
- [ ] PostgreSQL's `bin` folder on the system PATH, or backup and restore cannot run at all
- [ ] PostgreSQL not listening on a public interface
- [ ] `ENABLE_API_DOCS` left unset (the OpenAPI spec stays closed in production)

## Reverse proxy

Terminate TLS in front and proxy both processes from one origin, so the auth cookie is same-site:

```
/          → http://127.0.0.1:3000   (Next.js)
/api/      → http://127.0.0.1:5000   (Flask)
```

Pass `X-Forwarded-For` / `X-Forwarded-Proto`; the app trusts exactly one proxy hop (`ProxyFix` in `app/__init__.py`). Add a second hop there if you put a CDN in front of the proxy.

## Linux (systemd)

```bash
./scripts/install-linux.sh
sudo cp deploy/systemd/greentech-*.service /etc/systemd/system/
sudo systemctl enable --now greentech-backend greentech-frontend
# only with Redis configured:
sudo systemctl enable --now greentech-worker greentech-beat
```

The units expect the app at `/opt/greentech` running as user `greentech`, and read `backend/.env` via `EnvironmentFile`. `WAITRESS_LISTEN` decides whether the backend binds loopback (proxy on the same host) or `0.0.0.0` (separate proxy host — firewall port 5000 to it).

---

## Turning reminders on

Reminders are deliberately inert on a fresh install: `notifications.enabled` is off, `email.enabled` is off, `telegram.enabled` is off, and all seven rules ship disabled. Bringing them up, in this order:

1. **Settings → Email** — enter the SMTP details and press *Send a test email*. That test bypasses the send switch, so you can prove the credentials before any client can be written to.
2. **Settings → Notification rules** — open a rule, set its advance days, channels and audience, save it, and press **Preview**. Preview lists the exact addresses the rule would contact today and writes nothing.
3. Leave `email.enabled` **off** for a first run and use **Messages → Run sweep now**. Every message is composed and logged with status `skipped`; read them.
4. Optionally set `email.redirect_to` to your own address and switch sending on — a full run, real delivery, but everything lands in one inbox with the intended recipient named in the body.
5. Clear the redirect and switch `notifications.enabled` on. The sweep then runs itself at `notifications.send_hour` (UTC — Qatar is UTC+3, so `6` is 9am local), which needs Celery beat and therefore Redis.

A rule fires only on the exact day something is N days away, and each delivery carries a unique key, so a sweep run twice in one day sends nothing twice.

Telegram is internal only — the bot posts to the company's staff group and never to a client. The AI assistant drafts text for a person to review; it never sends anything by itself, and choosing the `local` provider keeps tenant names and figures on your own machine.

## Backups

`backup.folder`, `backup.schedule` and `backup.retention_days` are configured in **Settings → Backup** in the UI; backups can also be taken and restored from there. The scheduled job runs through Celery beat, so automatic backups need Redis. Manual backup and restore work without it.

A backup is a single `.zip` holding `database.dump` (custom pg_dump format), every file under `uploads/`, and a `manifest.json`. Database and documents are restored together — an attachment row stores a path relative to the uploads folder, so restoring one without the other leaves agreements and cheque copies that no longer open. Download the zip and keep it off the machine; that one file is the whole portal.

A bare `.dump` is also accepted on restore, for a dump taken with `pg_dump` by hand. It restores the database only, and the UI says so before and after.

Restore requires `pg_dump`, `pg_restore` and `psql` on the system PATH (add e.g. `C:\Program Files\PostgreSQL\18\bin`, then restart the backend service). It needs **no privilege beyond the ones the `greentech` role already holds on its own database** — objects are replaced inside the existing database and the database itself is never dropped. Do not grant the app role `CREATEDB` or superuser for backups to work.

Restoring replaces the live `uploads/` folder; the previous one is moved to a dated `uploads.pre-restore-<timestamp>` sibling rather than deleted, so a restore of the wrong archive is recoverable.

## Upgrading

```powershell
.\scripts\stop-all.ps1
git pull
.\scripts\install-windows.ps1     # refreshes deps, rebuilds the frontend
cd backend; .\.venv\Scripts\flask.exe --app wsgi migrate-all
.\scripts\start-all.ps1
```

`migrate-all` is idempotent — safe on every boot, a no-op when the schema is current.

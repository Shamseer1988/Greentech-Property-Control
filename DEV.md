# Local development

```cmd
:: First-time setup (Windows) — installs venv + builds frontend.
.\scripts\install-windows.ps1

:: Bootstrap the database (creates tables, runs phase migrations, seeds).
.\scripts\bootstrap-db.ps1

:: Start everything (opens 4 PowerShell windows).
.\scripts\start-all.ps1
```

Then open **http://localhost:3000** — login `admin` /
`<SUPERUSER_PASSWORD value from backend\.env>`.

The windows are: backend (waitress on 127.0.0.1:5000), Next.js frontend
(127.0.0.1:3000), plus Celery worker and beat when `REDIS_URL` is set.
Tail each window for real-time logs.

## System prerequisites (one-time, see `docs/DEPLOYMENT.md`)

- PostgreSQL 17+ — official Windows installer.
- Python 3.11 — with "Add to PATH" checked.
- Node 20 LTS.
- Redis — **optional until Phase 7**. Memurai (recommended) or WSL2 +
  redis-server. Without `REDIS_URL` in `backend\.env` the rate limiter
  falls back to an in-memory store and `start-all.ps1` skips the Celery
  worker/beat windows. Scheduled expiry sweeps and reminder emails need
  it; nothing else does.

## Stop everything

```cmd
.\scripts\stop-all.ps1
```

## Re-run after pulling new code

```cmd
.\scripts\stop-all.ps1
git pull
.\scripts\install-windows.ps1     :: refreshes deps if requirements changed
.\scripts\start-all.ps1
```

## Iterating on code

- **Backend hot-reload** — stop the backend window, restart manually:
  ```cmd
  cd backend
  .venv\Scripts\python.exe wsgi.py    :: dev server with debug reload
  ```
- **Frontend hot-reload** — by default `npm start` runs the prod build.
  For HMR, stop the frontend window and run:
  ```cmd
  cd frontend
  npm run dev
  ```
  Opens on port 3000 with file-watching.

## Tests

Backend:
```cmd
cd backend
.venv\Scripts\pytest -q
```

Frontend:
```cmd
cd frontend
npm run type-check
npm test
```

## Linux / macOS

Same shape, different shell:

```bash
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
(cd frontend && npm ci && npm run build)
flask --app backend.wsgi init-db
flask --app backend.wsgi seed
waitress-serve --listen=127.0.0.1:5000 --threads=8 backend.wsgi:app  # in one shell
(cd frontend && npm start)                                            # in another
celery -A backend.celery_worker.celery worker --loglevel=info        # in another
celery -A backend.celery_worker.celery beat   --loglevel=info        # in another
```

Production deployment is documented in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

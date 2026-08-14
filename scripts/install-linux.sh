#!/usr/bin/env bash
# One-time install of the bare-metal dependencies on Linux (Debian/Ubuntu).
# Run from the REPO ROOT:
#     bash scripts/install-linux.sh
#
# What this script does:
#  1. Verifies python3.11, node, npm, and psql are on PATH.
#  2. Creates a Python venv under backend/.venv and installs requirements.
#  3. Runs `npm ci` + `npm run build` for the frontend.
#  4. Seeds backend/.env from backend/.env.example on first run.
#
# It does NOT install PostgreSQL / Redis / nginx — those are operator
# steps documented in docs/DEPLOYMENT.md.

set -euo pipefail

# ldconfig lives in /sbin or /usr/sbin — not on a non-root login shell's
# PATH by default on Debian, so the libmagic probe below would fall
# through silently. Prepend both unconditionally; this is a no-op if
# they're already there.
export PATH="/usr/sbin:/sbin:$PATH"

# Move to repo root regardless of where the script was invoked from.
cd "$(dirname "$0")/.."

say() { printf '\033[36m=== %s ===\033[0m\n' "$*"; }

# -----------------------------------------------------------------------------
# Resolve Python 3.11.
# -----------------------------------------------------------------------------
say "Resolving Python 3.11"
PYTHON=""
for cand in python3.11 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        if [[ "$ver" == "3.11" || "$ver" > "3.11" ]]; then
            PYTHON="$cand"
            echo "  using $cand ($("$cand" --version))"
            break
        fi
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python 3.11+ not found. See docs/DEPLOYMENT.md." >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# Other prereqs — just check they're on PATH.
# -----------------------------------------------------------------------------
say "Other prereqs"
for cmd in node npm psql; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: $cmd not found in PATH. Install it (see docs/DEPLOYMENT.md) and re-run." >&2
        exit 1
    fi
    echo "  $cmd : $(command -v "$cmd")"
done

# libmagic — python-magic needs the system shared lib at import time.
if ! ldconfig -p 2>/dev/null | grep -q 'libmagic\.so'; then
    echo "ERROR: libmagic shared library missing." >&2
    echo "       sudo apt-get install -y libmagic1" >&2
    exit 1
fi
echo "  libmagic : found"

# -----------------------------------------------------------------------------
# Create / update the venv.
# -----------------------------------------------------------------------------
say "Backend venv"
if [[ ! -x "backend/.venv/bin/python" ]]; then
    echo "  creating backend/.venv …"
    "$PYTHON" -m venv backend/.venv
    if [[ ! -x "backend/.venv/bin/python" ]]; then
        echo "ERROR: venv creation failed. Is python3.11-venv installed? (apt install python3.11-venv)" >&2
        exit 1
    fi
else
    echo "  backend/.venv already exists — reusing."
fi

backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# -----------------------------------------------------------------------------
# Frontend.
# -----------------------------------------------------------------------------
say "Frontend build"
(cd frontend && npm ci && npm run build)

# -----------------------------------------------------------------------------
# Seed backend/.env on first run.
# -----------------------------------------------------------------------------
say "backend/.env"
if [[ ! -f "backend/.env" ]]; then
    cp backend/.env.example backend/.env
    echo "  copied backend/.env.example -> backend/.env"
    echo "  EDIT backend/.env to set strong SECRET_KEY / JWT_SECRET_KEY / POSTGRES_PASSWORD before bootstrapping."
else
    echo "  backend/.env already exists — left alone."
fi

# -----------------------------------------------------------------------------
# Seed frontend/.env.runtime on first run. Optional — the systemd unit
# falls back to topology-A defaults if this file is missing. Operators
# only need to edit it when flipping HOSTNAME for topology B.
# -----------------------------------------------------------------------------
say "frontend/.env.runtime"
if [[ ! -f "frontend/.env.runtime" ]]; then
    cp frontend/.env.runtime.example frontend/.env.runtime
    echo "  copied frontend/.env.runtime.example -> frontend/.env.runtime"
    echo "  For topology B (shared edge-nginx CT) set HOSTNAME=0.0.0.0 in this file."
else
    echo "  frontend/.env.runtime already exists — left alone."
fi

printf '\n\033[32mDone.\033[0m Next steps:\n'
echo "  1. Edit backend/.env (secrets, DB password)."
echo "  2. Create the Postgres database + role (see docs/DEPLOYMENT.md)."
echo "  3. Run: bash scripts/bootstrap-db.sh        (one-time schema + seed)"
echo "  4. Run: bash scripts/start-all.sh           (dev) — OR install systemd units (prod)."

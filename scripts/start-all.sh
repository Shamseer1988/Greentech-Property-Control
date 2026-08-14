#!/usr/bin/env bash
# Start every process the portal needs, in the right order.
#
# This is the DEV / smoke-test launcher. For real production use the
# systemd units under deploy/systemd/ — see docs/DEPLOYMENT.md.
#
# Logs go to /tmp/greentech-*.log so you can `tail -f` them.
# Run `bash scripts/stop-all.sh` to kill everything.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PIDFILE="/tmp/greentech-pids"
: > "$PIDFILE"

LISTEN="${WAITRESS_LISTEN:-127.0.0.1:5000}"
THREADS="${WAITRESS_THREADS:-8}"

launch() {
    local name=$1; local logfile=$2; local workdir=$3; shift 3
    echo "  starting $name → $logfile"
    (cd "$workdir" && exec "$@" >"$logfile" 2>&1) &
    local pid=$!
    echo "$name $pid" >> "$PIDFILE"
}

printf '\033[36mStarting backend / worker / beat / frontend …\033[0m\n'

launch greentech-backend  /tmp/greentech-backend.log  "$BACKEND" \
    "$BACKEND/.venv/bin/waitress-serve" --listen="$LISTEN" --threads="$THREADS" wsgi:app

sleep 3

launch greentech-worker   /tmp/greentech-worker.log   "$BACKEND" \
    "$BACKEND/.venv/bin/celery" -A celery_worker.celery worker --loglevel=info

launch greentech-beat     /tmp/greentech-beat.log     "$BACKEND" \
    "$BACKEND/.venv/bin/celery" -A celery_worker.celery beat --loglevel=info \
    --schedule=/tmp/celerybeat-schedule

launch greentech-frontend /tmp/greentech-frontend.log "$FRONTEND" \
    npm start

cat <<EOF

PIDs recorded in $PIDFILE.
Tail logs:
  tail -f /tmp/greentech-backend.log
  tail -f /tmp/greentech-frontend.log
Health:
  curl http://127.0.0.1:5000/api/v1/health
  curl http://127.0.0.1:3000
Stop:
  bash scripts/stop-all.sh
EOF

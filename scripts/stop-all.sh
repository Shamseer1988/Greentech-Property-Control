#!/usr/bin/env bash
# Stop every process started by start-all.sh.
set -u
PIDFILE="/tmp/greentech-pids"

if [[ -f "$PIDFILE" ]]; then
    while read -r name pid; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "  stopping $name (PID $pid)"
            kill "$pid" 2>/dev/null || true
        fi
    done < "$PIDFILE"
    rm -f "$PIDFILE"
fi

# Belt-and-braces: kill any orphaned waitress / celery / next processes
# whose cwd is inside this repo. Matches what stop-all.ps1 does.
REPO="$(cd "$(dirname "$0")/.." && pwd)"
for pid in $(pgrep -f 'waitress-serve|celery|node' || true); do
    if [[ -r "/proc/$pid/cwd" ]] && readlink "/proc/$pid/cwd" 2>/dev/null | grep -qF "$REPO"; then
        echo "  killing stray PID $pid"
        kill "$pid" 2>/dev/null || true
    fi
done

echo "Done."

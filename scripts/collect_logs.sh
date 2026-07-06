#!/usr/bin/env bash
# Copies the backend's on-disk log files (from the `backend_logs` Docker
# volume) to /tmp so they can be grepped without going through `docker logs`
# (which only shows the current container's stdout, and is lost on restart).
#
# Usage:
#   ./scripts/collect_logs.sh                    # copy all logs to /tmp
#   ./scripts/collect_logs.sh shiprocket          # copy, then grep -i for a term
#   ./scripts/collect_logs.sh shiprocket -A2 -B1  # extra args passed to grep
set -euo pipefail

CONTAINER="${CONTAINER:-chokmoki-backend}"
DEST_DIR="/tmp/chokmoki-logs-$(date +%Y%m%d-%H%M%S)"
TERM="${1:-}"
if [ "$#" -gt 0 ]; then
  shift
fi

mkdir -p "$DEST_DIR"
docker cp "${CONTAINER}:/app/logs/." "$DEST_DIR/"

echo "Logs copied to: $DEST_DIR"
ls -la "$DEST_DIR"

if [ -n "$TERM" ]; then
  echo
  echo "--- grep -i '$TERM' ---"
  grep -ri "$TERM" "$@" "$DEST_DIR"/*.log || echo "(no matches)"
fi

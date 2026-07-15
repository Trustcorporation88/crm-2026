#!/bin/sh
set -e

# Prefer explicit CRM_DATA_DIR; otherwise use Railway/Render volume at /data when present.
if [ -z "${CRM_DATA_DIR:-}" ]; then
  if [ -d /data ]; then
    export CRM_DATA_DIR=/data
  else
    export CRM_DATA_DIR=/app/Data
  fi
fi

mkdir -p "$CRM_DATA_DIR"

if [ "$(id -u)" = "0" ]; then
  # Volume mounts are often root-owned; SQLite needs a writable directory for the DB + journal/WAL.
  chown -R streamlit:streamlit "$CRM_DATA_DIR" 2>/dev/null || true
  chmod -R u+rwX "$CRM_DATA_DIR" 2>/dev/null || true
  exec gosu streamlit "$@"
fi

exec "$@"

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

# Ensure SQLite can create the DB + journal/WAL next to it.
fix_data_perms() {
  chmod -R a+rwX "$CRM_DATA_DIR" 2>/dev/null || true
  find "$CRM_DATA_DIR" -type f \( -name '*.sqlite3' -o -name '*.db' -o -name '*-wal' -o -name '*-shm' -o -name '*.journal' \) \
    -exec chmod a+rw {} \; 2>/dev/null || true
}

if [ "$(id -u)" = "0" ]; then
  # Volume mounts are often root-owned; chown may be ignored on some volume backends.
  chown -R streamlit:streamlit "$CRM_DATA_DIR" 2>/dev/null || true
  fix_data_perms
  if gosu streamlit sh -c "touch \"$CRM_DATA_DIR/.write_test\" && rm -f \"$CRM_DATA_DIR/.write_test\""; then
    exec gosu streamlit "$@"
  fi
  echo "WARN: $CRM_DATA_DIR not writable as uid streamlit; starting as root" >&2
  exec "$@"
fi

fix_data_perms
exec "$@"

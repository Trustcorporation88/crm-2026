"""One-shot SQLite export for Render → Railway migration.

Set CRM_MIGRATION_TOKEN and run on PORT (replaces Streamlit temporarily):
  CRM_MIGRATION_TOKEN=... python migration_export_server.py

Download:
  curl -fsSL "http://host/export?token=TOKEN" -o crm.sqlite3
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from crm_backend import DB_PATH


def main() -> None:
    token = os.getenv("CRM_MIGRATION_TOKEN", "").strip()
    if not token:
        print("CRM_MIGRATION_TOKEN is required", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(DB_PATH):
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    port = int(os.getenv("PORT", "8512"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/_stcore/health", "/health"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")
                return

            if self.path != f"/export?token={token}":
                self.send_response(404)
                self.end_headers()
                return

            with open(DB_PATH, "rb") as handle:
                payload = handle.read()

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="crm.sqlite3"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Migration export server on 0.0.0.0:{port} (db={DB_PATH})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

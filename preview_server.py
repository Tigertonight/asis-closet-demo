"""Minimal static preview server for the selfit onboarding frontend.

Replicates only the FastAPI `/selfit` route + `/static` mount so the page's
styles can be viewed without loading the heavy backend. Uses apiMode=mock so
the full flow runs offline. Adds nothing to the real app.
"""
import http.server
import json
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "app" / "static"
INDEX = STATIC_DIR / "selfit" / "index.html"
PORT = 8747

CONFIG = {
    "apiMode": "mock",
    "apiBase": "/api/v1/selfit",
    "authMode": "mock",
    "authBase": "/auth",
    "timeoutMs": 15000,
}


def selfit_html() -> bytes:
    html = INDEX.read_text(encoding="utf-8")
    tag = "<script>window.__SELFIT_CONFIG__ = " + json.dumps(CONFIG, ensure_ascii=False) + ";</script>"
    marker = '<script src="/static/selfit/selfit-api.js'
    if marker in html:
        html = html.replace(marker, tag + marker, 1)
    return html.encode("utf-8")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "app"), **kwargs)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/selfit", "/selfit/", "/selfit/demo"):
            body = selfit_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"selfit preview on http://127.0.0.1:{PORT}/selfit")
        httpd.serve_forever()

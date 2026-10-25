"""Small loopback-only HTTP service; no dependency installation needed."""
from datetime import datetime, timezone
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from . import analysis, research, storage, ingest

ROOT = Path(__file__).resolve().parent.parent


def dashboard(db_path):
    storage.register_sources(db_path, ingest.SOURCES)
    account_path = ROOT / "config" / "accounts.json"
    access_path = ROOT / "config" / "x_access.json"
    accounts = json.loads(account_path.read_text(encoding="utf-8")) if account_path.exists() else {}
    x_access = json.loads(access_path.read_text(encoding="utf-8")) if access_path.exists() else {"status": "not_checked", "automatic": False, "can_capture": True, "detail": "Browser X access has not been checked."}
    return analysis.compose({**storage.dashboard_data(db_path), **research.read(db_path), "accounts": accounts.get("accounts", []) if isinstance(accounts, dict) else accounts, "x_access": x_access})


def refresh(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with (db_path.parent / ".refresh.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A refresh is already running; wait for it to finish")
        result = ingest.refresh(db_path)
        snapshot = dashboard(db_path)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stamp = datetime.now(timezone.utc).strftime("%H%M%S-%f")
        folder = db_path.parent / "daily" / day
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (stamp + ".json")).write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        return result


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AIStockPulse/0.2"

        def allowed(self):
            host = self.headers.get("Host", "")
            port = self.server.server_address[1]
            return host in ("127.0.0.1:%s" % port, "localhost:%s" % port)

        def respond(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {"error": "Loopback Host required"})
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    return self.respond(200, {"status": "ok", "version": "0.2.0", "local_only": True})
                if path == "/api/dashboard":
                    return self.respond(200, dashboard(db_path))
                routes = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/styles.css": ("styles.css", "text/css")}
                routes.update({"/"+name:(name,"text/javascript" if name.endswith(".js") else "text/css") for name in ("finance.js","finance.css","visit-state.js")})
                if path in routes:
                    name, mime = routes[path]
                    return self.respond(200, (ROOT / "static" / name).read_bytes(), mime + "; charset=utf-8")
                if path == "/favicon.ico":
                    return self.respond(204, b"", "image/x-icon")
                return self.respond(404, {"error": "Not found"})
            except Exception as exc:
                self.log_error("GET failed: %s", exc)
                return self.respond(500, {"error": "Local data could not be read. Check the terminal for details."})

        def do_POST(self):
            port = self.server.server_address[1]
            origin = self.headers.get("Origin")
            if not self.allowed() or (origin and origin not in ("http://127.0.0.1:%s" % port, "http://localhost:%s" % port)):
                return self.respond(403, {"error": "Only same-origin local requests are accepted"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.respond(415, {"error": "Content-Type application/json required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 12000:
                    return self.respond(413, {"error": "Request too large"})
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("JSON object required")
                path = urlsplit(self.path).path
                if path == "/api/refresh":
                    return self.respond(200, refresh(db_path))
                if path == "/api/leads":
                    return self.respond(200, research.add_lead(db_path, payload.get("url"), payload.get("note", "")))
                if path == "/api/review":
                    if "article_ids" in payload:
                        return self.respond(200, research.review_articles(db_path, payload["article_ids"], payload.get("status")))
                    return self.respond(200, research.review_article(db_path, payload.get("article_id"), payload.get("status")))
                return self.respond(404, {"error": "Not found"})
            except (ValueError, TypeError) as exc:
                return self.respond(400, {"error": str(exc)})
            except RuntimeError as exc:
                return self.respond(409, {"error": str(exc)})
            except Exception as exc:
                self.log_error("POST failed: %s", exc)
                return self.respond(500, {"error": "Operation failed. Existing evidence is retained; check terminal details."})

    return Handler


def serve(db_path, port=8765):
    storage.initialize(db_path)
    research.initialize(db_path)
    handler = make_handler(db_path)
    server = None
    for candidate in range(port, min(port + 30, 65536)):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            break
        except OSError as exc:
            if exc.errno not in (48, 98):
                raise
    if server is None:
        raise RuntimeError("No unused local port in requested range")
    print("AI Stock Pulse: http://127.0.0.1:%s" % server.server_address[1], flush=True)
    print("Local database: %s" % db_path, flush=True)
    print("Press Ctrl-C to stop. Refresh is manual; no background schedule is installed.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

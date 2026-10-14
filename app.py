"""GitPublish — local web dashboard (zero dependencies, stdlib http.server).

Run:  python3 app.py            -> opens http://localhost:5060
Set a different projects root:  PROJECTS_ROOT=~/code python3 app.py
Your GitHub token stays on this machine (0600 file) and is never sent anywhere
except api.github.com.
"""
from __future__ import annotations
import html, json, os, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import ghcore as C

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT = os.path.expanduser(os.environ.get("PROJECTS_ROOT", "~/Documents/Projects_Folder"))


def render():
    with open(os.path.join(BASE, "templates", "dashboard.html"), encoding="utf-8") as f:
        return f.read().replace("__ROOT__", html.escape(PROJECTS_ROOT))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200): self._send(code, json.dumps(obj))

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n: return {}
        try: return json.loads(self.rfile.read(n).decode())
        except Exception: return {}

    def do_GET(self):
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if path == "/":
            self._send(200, render(), "text/html; charset=utf-8")
        elif path == "/api/status":
            t = C.get_token()
            self._json({"token": bool(t), "user": C.whoami(t) if t else None})
        elif path == "/api/repos":
            t = C.get_token()
            self._json({"repos": C.list_repos(t) if t else [], "user": C.whoami(t) if t else None})
        elif path == "/api/projects":
            root = qs.get("root", [PROJECTS_ROOT])[0]
            self._json({"root": root, "projects": C.scan_projects(root)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        b = self._body()
        if path == "/api/login":
            tok = (b.get("token") or "").strip()
            if not tok: return self._json({"ok": False, "error": "empty token"})
            who = C.whoami(tok)
            if not who: return self._json({"ok": False, "error": "GitHub rejected this token (needs 'repo' scope)"})
            C.save_token(tok)
            self._json({"ok": True, "user": who})
        elif path == "/api/publish":
            t = C.get_token()
            if not t: return self._json({"ok": False, "error": "no token"})
            res = C.publish_folder(t, b["path"], name=b.get("name") or None,
                                   private=bool(b.get("private")), desc=b.get("desc", ""))
            self._json(res)
        elif path == "/api/make_public":
            t = C.get_token(); login = C.whoami(t)
            ok, j = C.set_visibility(t, login, b["name"], False)
            self._json({"ok": ok, "error": None if ok else j.get("message")})
        elif path == "/api/make_public_all":
            t = C.get_token()
            self._json({"results": C.make_all_public(t)})
        else:
            self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    want = int(os.environ.get("PORT", 5060))
    # find a free port (auto-increment if the chosen one is busy)
    httpd = None
    for port in range(want, want + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if httpd is None:
        print(f"[gitpublish] no free port in {want}..{want+19}. Set PORT=<n> and retry.")
        raise SystemExit(1)
    url = f"http://localhost:{port}"
    if port != want:
        print(f"[gitpublish] port {want} was busy — using {port} instead")
    print(f"[gitpublish] {url}  (projects root: {PROJECTS_ROOT})")
    print("[gitpublish] your token stays local; nothing is sent except to api.github.com")
    if os.environ.get("GITPUBLISH_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[gitpublish] stopped.")

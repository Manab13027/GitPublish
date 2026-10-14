"""GitPublish — local web dashboard (zero dependencies, stdlib http.server).

Run:  python3 app.py            -> opens http://127.0.0.1:5060
Set a different projects root:  PROJECTS_ROOT=~/code python3 app.py
Your GitHub token stays on this machine (0600 file) and is never sent anywhere
except api.github.com.
"""
from __future__ import annotations
import html, http.client, json, os, socket, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import ghcore as C

# When frozen by PyInstaller, bundled data (templates/) lives under _MEIPASS.
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
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
        elif path == "/api/ignore":
            lst = C.set_ignored(b["path"], bool(b.get("ignore", True)))
            self._json({"ok": True, "ignored": lst})
        else:
            self._json({"error": "not found"}, 404)


def _in_use(p: int) -> bool:
    """True if something is already listening on 127.0.0.1:p."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.25)
    try:
        s.connect(("127.0.0.1", p))
        return True          # someone answered -> occupied
    except OSError:
        return False         # refused -> free
    finally:
        try: s.close()
        except Exception: pass


if __name__ == "__main__":
    want = int(os.environ.get("PORT", 5060))
    # pick the first genuinely-free port by probing for a live listener first,
    # so we never collide with an already-running GitPublish.
    httpd = None
    for port in range(want, want + 25):
        if _in_use(port):
            continue
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if httpd is None:
        print(f"[gitpublish] no free port in {want}..{want+24}. "
              f"Stop old instances:  pkill -f app.py   then retry.")
        raise SystemExit(1)
    url = f"http://127.0.0.1:{port}"
    if port != want:
        print(f"[gitpublish] port {want} was busy — using {port} instead "
              f"(tip: 'pkill -f app.py' first to always get {want})")

    # serve in a background thread so we can self-test that it's really listening
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        c.request("GET", "/"); r = c.getresponse(); ok = (r.status == 200); c.close()
    except Exception as e:
        ok = False; print(f"[gitpublish] SELF-TEST FAILED: {e}")
    print("")
    print("  ┌────────────────────────────────────────────────┐")
    print(f"  │  OPEN THIS IN YOUR BROWSER:  {url:<18} │")
    print("  └────────────────────────────────────────────────┘")
    print(f"  self-test: {'OK — the server is serving this page.' if ok else 'the server is NOT reachable (see error above).'}")
    print(f"  (projects root: {PROJECTS_ROOT})")
    print("  your token stays local; nothing is sent except to api.github.com")
    print("  press Ctrl+C to stop.\n")
    if ok and os.environ.get("GITPUBLISH_NO_BROWSER") != "1":
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[gitpublish] stopped.")

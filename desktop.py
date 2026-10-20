"""GitPublish desktop app entry point.

Runs the same local dashboard as app.py, but inside its own native window
(pywebview / WKWebView on macOS) instead of a browser tab — so it behaves like
a normal Mac app: Dock icon, Cmd+Q, closing the window quits.

If pywebview isn't available (e.g. a Linux/Windows build), it falls back to
opening the dashboard in the default browser.

    python3 desktop.py              # dev run
    bash packaging/build_app.sh     # -> dist/GitPublish.app + dist/GitPublish.dmg
"""
from __future__ import annotations
import os, sys, threading, time, webbrowser

FROZEN = getattr(sys, "frozen", False)
LOG = os.path.expanduser("~/Library/Logs/GitPublish.log")

if FROZEN:  # no Terminal when launched from Finder: send output to a log file
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        sys.stdout = sys.stderr = open(LOG, "a", buffering=1, encoding="utf-8")
        print(f"\n=== GitPublish start {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    except Exception:
        pass


def _fix_env_for_finder_launch() -> None:
    """Apps started from Finder/Dock get a bare environment. Patch it up."""
    # 1. PATH: Finder gives /usr/bin:/bin:/usr/sbin:/sbin — add Homebrew so a
    #    brew-installed git is found too (Apple's /usr/bin/git still works).
    extra = ["/opt/homebrew/bin", "/usr/local/bin"]
    parts = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(":")
    os.environ["PATH"] = ":".join([p for p in extra if p not in parts] + parts)

    # 2. HTTPS certificates: a frozen Python carries its own OpenSSL whose
    #    default CA path may not exist on another Mac (CERTIFICATE_VERIFY_FAILED
    #    when talking to api.github.com). macOS ships a CA bundle — use it.
    if not os.environ.get("SSL_CERT_FILE"):
        import ssl
        default = ssl.get_default_verify_paths().cafile
        if not default or not os.path.exists(default):
            for cand in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
                if os.path.exists(cand):
                    os.environ["SSL_CERT_FILE"] = cand
                    break


_fix_env_for_finder_launch()

from http.server import ThreadingHTTPServer  # noqa: E402
import app as server                          # noqa: E402  (reuses the dashboard handler)


def start_server() -> tuple[ThreadingHTTPServer, str]:
    want = int(os.environ.get("PORT", 5060))
    for port in range(want, want + 25):
        if server._in_use(port):
            continue
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), server.H)
        except OSError:
            continue
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, f"http://127.0.0.1:{port}"
    raise SystemExit(f"[gitpublish] no free port in {want}..{want + 24}")


def self_test(url: str) -> str | None:
    """GET / from our own server. Returns an error string, or None if OK."""
    import http.client
    from urllib.parse import urlparse
    u = urlparse(url)
    for _ in range(20):
        try:
            c = http.client.HTTPConnection(u.hostname, u.port, timeout=3)
            c.request("GET", "/"); r = c.getresponse(); body = r.read(); c.close()
            if r.status == 200 and b"<html" in body[:400].lower():
                return None
            return f"server answered HTTP {r.status}: {body[:300]!r}"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            time.sleep(0.15)
    return err


def _alert(msg: str) -> None:
    if sys.platform == "darwin":
        import subprocess
        safe = msg.replace("\\", "/").replace('"', "'")
        subprocess.run(["osascript", "-e", f'display alert "GitPublish" message "{safe}"'],
                       capture_output=True)
    print(msg)


def main() -> None:
    if not any(os.access(os.path.join(d, "git"), os.X_OK) for d in os.environ["PATH"].split(":")):
        _alert("git was not found. Install Apple's command line tools (xcode-select --install) and relaunch.")

    httpd, url = start_server()
    print(f"[gitpublish] server {url}  templates={server.BASE}")
    err = self_test(url)
    if err:
        _alert(f"GitPublish's local server failed: {err}  (details: {LOG})")
        raise SystemExit(1)

    try:
        import webview  # pywebview
    except Exception:
        webview = None

    if webview is not None and os.environ.get("GITPUBLISH_BROWSER") != "1":
        storage = os.path.expanduser("~/.config/gitpublish/webview")
        os.makedirs(storage, exist_ok=True)
        debug = os.environ.get("GITPUBLISH_DEBUG") == "1"   # right-click -> Inspect Element
        webview.create_window("GitPublish", url, width=1200, height=820,
                              min_size=(900, 600), text_select=True)
        webview.start(private_mode=False, storage_path=storage, debug=debug)  # blocks until closed
        httpd.shutdown()
        return

    # ---- fallback: browser tab, keep serving until Ctrl+C / killed
    print(f"[gitpublish] serving {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()

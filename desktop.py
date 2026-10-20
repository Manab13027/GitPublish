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


def _alert(msg: str) -> None:
    if sys.platform == "darwin":
        os.system("osascript -e " + repr(f'display alert "GitPublish" message "{msg}"') + " >/dev/null 2>&1")
    print(msg)


def main() -> None:
    if not any(os.access(os.path.join(d, "git"), os.X_OK) for d in os.environ["PATH"].split(":")):
        _alert("git was not found. Install Apple's command line tools (xcode-select --install) and relaunch.")

    httpd, url = start_server()
    time.sleep(0.2)

    try:
        import webview  # pywebview
    except Exception:
        webview = None

    if webview is not None and os.environ.get("GITPUBLISH_BROWSER") != "1":
        storage = os.path.expanduser("~/.config/gitpublish/webview")
        os.makedirs(storage, exist_ok=True)
        webview.create_window("GitPublish", url, width=1200, height=820,
                              min_size=(900, 600), text_select=True)
        webview.start(private_mode=False, storage_path=storage)  # blocks until window closes
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

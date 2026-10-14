"""GitPublish core — GitHub API + git operations. Standard library only.

Design goals:
  * Zero dependencies (urllib for the API, subprocess for git).
  * The token stays on this machine. It is read from the environment or a
    0600 file under ~/.config/gitpublish/token, never written into a repo,
    and never persisted in .git/config (pushes use a one-shot auth header).
  * Safe by default: auto-generates a sensible .gitignore and refuses to
    commit files GitHub would reject (>95 MB), listing them instead.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
import urllib.error

API = "https://api.github.com"
CONFIG_DIR = os.path.expanduser("~/.config/gitpublish")
TOKEN_FILE = os.path.join(CONFIG_DIR, "token")
GH_MAX_BYTES = 95 * 1024 * 1024  # GitHub hard-rejects files >100MB; stay under

DEFAULT_GITIGNORE = """\
# --- GitPublish defaults ---
__pycache__/
*.py[cod]
.venv/
venv/
.env
node_modules/
dist/
build/
*.log
.DS_Store
# large media / build artifacts
*.mp4
*.mov
*.aiff
*.wav
*.zip
*.rar
*.tif
*.tiff
*.iso
*.dmg
*.exe
# secrets
*.pem
*.key
token
.gitpublish_token
"""


# -------------------------------------------------------------- token
def get_token() -> str | None:
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var].strip()
    if os.path.exists(TOKEN_FILE):
        try:
            return open(TOKEN_FILE).read().strip()
        except Exception:
            return None
    return None


def save_token(tok: str) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(tok.strip())
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass


# -------------------------------------------------------------- API
def api(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "GitPublish")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw}
    except Exception as e:
        return 0, {"message": str(e)}


def whoami(token: str) -> str | None:
    code, j = api("GET", "/user", token)
    return j.get("login") if code == 200 else None


def list_repos(token: str, per_page: int = 100) -> list[dict]:
    repos, page = [], 1
    while True:
        code, j = api("GET", f"/user/repos?per_page={per_page}&page={page}&affiliation=owner&sort=pushed", token)
        if code != 200 or not j:
            break
        repos.extend({"name": r["name"], "full_name": r["full_name"], "private": r["private"],
                      "html_url": r["html_url"], "pushed_at": r.get("pushed_at")} for r in j)
        if len(j) < per_page:
            break
        page += 1
    return repos


def create_repo(token: str, name: str, private: bool, desc: str = "") -> tuple[bool, dict]:
    code, j = api("POST", "/user/repos", token,
                  {"name": name, "private": private, "description": desc, "auto_init": False})
    if code in (200, 201):
        return True, j
    if code == 422:  # already exists
        login = whoami(token)
        c2, j2 = api("GET", f"/repos/{login}/{name}", token)
        if c2 == 200:
            return True, j2
    return False, j


def set_visibility(token: str, owner: str, name: str, private: bool) -> tuple[bool, dict]:
    code, j = api("PATCH", f"/repos/{owner}/{name}", token, {"private": private})
    return code == 200, j


def make_all_public(token: str) -> list[dict]:
    login = whoami(token)
    out = []
    for r in list_repos(token):
        if r["private"]:
            ok, j = set_visibility(token, login, r["name"], False)
            out.append({"name": r["name"], "ok": ok, "error": None if ok else j.get("message")})
    return out


# -------------------------------------------------------------- git
def _run(args: list[str], cwd: str, token: str | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    out = (p.stdout or "") + (p.stderr or "")
    if token:  # never echo the token
        out = out.replace(token, "***")
    return p.returncode, out.strip()


def ensure_gitignore(folder: str) -> None:
    gi = os.path.join(folder, ".gitignore")
    if not os.path.exists(gi):
        open(gi, "w").write(DEFAULT_GITIGNORE)


def _is_ignored(folder: str, relpath: str) -> bool:
    code, _ = _run(["git", "check-ignore", "-q", relpath], folder)
    return code == 0


def find_large_files(folder: str) -> list[str]:
    """Files over GitHub's limit that are NOT already ignored."""
    big = []
    for root, dirs, files in os.walk(folder):
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                if os.path.getsize(fp) > GH_MAX_BYTES:
                    rel = os.path.relpath(fp, folder)
                    if not _is_ignored(folder, rel):
                        big.append(rel)
            except OSError:
                pass
    return big


def publish_folder(token: str, folder: str, name: str | None = None,
                   private: bool = False, desc: str = "", commit_msg: str = "Initial commit via GitPublish"):
    """Create (or reuse) the repo and push the folder. Returns a result dict."""
    log = []
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        return {"ok": False, "error": f"not a folder: {folder}", "log": log}
    name = name or os.path.basename(folder.rstrip("/"))

    login = whoami(token)
    if not login:
        return {"ok": False, "error": "bad or missing token (could not read GitHub user)", "log": log}

    ensure_gitignore(folder)

    # guard: auto-ignore files GitHub would reject, so the push can't fail on size
    big = find_large_files(folder)
    if big:
        with open(os.path.join(folder, ".gitignore"), "a") as f:
            f.write("\n# auto-excluded (over GitHub's 100MB limit)\n")
            for rel in big:
                f.write(rel + "\n")
        log.append(f"excluded {len(big)} oversized file(s): " + ", ".join(big[:5]) + ("…" if len(big) > 5 else ""))

    # create / reuse repo
    ok, repo = create_repo(token, name, private, desc)
    if not ok:
        return {"ok": False, "error": "create repo failed: " + str(repo.get("message")), "log": log}
    html_url = repo["html_url"]
    clone_url = f"https://github.com/{login}/{name}.git"

    # init + commit
    if not os.path.isdir(os.path.join(folder, ".git")):
        _run(["git", "init"], folder); log.append("git init")
    _run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], folder)
    _run(["git", "add", "-A"], folder)
    code, out = _run(["git", "commit", "-m", commit_msg], folder)
    log.append("commit: " + (out.splitlines()[0] if out else "nothing to commit"))

    # remote (clean URL, no token stored)
    _run(["git", "remote", "remove", "origin"], folder)
    _run(["git", "remote", "add", "origin", clone_url], folder)

    # push with a one-shot auth header (token never written to .git/config)
    header = f"Authorization: Bearer {token}"
    code, out = _run(["git", "-c", f"http.extraheader={header}", "push", "-u", "origin", "main", "--force"], folder, token)
    log.append("push: " + (out.splitlines()[-1] if out else "ok"))
    if code != 0:
        return {"ok": False, "error": "push failed: " + out, "html_url": html_url, "log": log}

    return {"ok": True, "html_url": html_url, "name": name, "private": private,
            "excluded_large": big, "log": log}


def scan_projects(root: str) -> list[dict]:
    """List immediate subfolders of `root` that look like projects."""
    root = os.path.abspath(os.path.expanduser(root))
    out = []
    if not os.path.isdir(root):
        return out
    for entry in sorted(os.listdir(root)):
        p = os.path.join(root, entry)
        if not os.path.isdir(p) or entry.startswith("."):
            continue
        is_git = os.path.isdir(os.path.join(p, ".git"))
        has_remote = False
        if is_git:
            code, out_r = _run(["git", "remote", "-v"], p)
            has_remote = bool(out_r.strip())
        out.append({"name": entry, "path": p, "is_git": is_git, "has_remote": has_remote})
    return out

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

import datetime
import json
import os
import subprocess
import urllib.request
import urllib.error

import readme_gen
import license_gen

API = "https://api.github.com"
CONFIG_DIR = os.path.expanduser("~/.config/gitpublish")
TOKEN_FILE = os.path.join(CONFIG_DIR, "token")
IGNORE_FILE = os.path.join(CONFIG_DIR, "ignored.json")
AUTHOR_FILE = os.path.join(CONFIG_DIR, "author")
GH_MAX_BYTES = 95 * 1024 * 1024  # GitHub hard-rejects files >100MB; stay under

DEFAULT_GITIGNORE = """\
# --- GitPublish defaults ---
__pycache__/
*.py[cod]
.venv/
venv/
.build-venv/
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


# -------------------------------------------------------------- ignore list
def load_ignored() -> list[str]:
    try:
        return list(json.load(open(IGNORE_FILE)))
    except Exception:
        return []


def set_ignored(path: str, ignore: bool) -> list[str]:
    path = os.path.abspath(os.path.expanduser(path))
    cur = set(load_ignored())
    if ignore:
        cur.add(path)
    else:
        cur.discard(path)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    json.dump(sorted(cur), open(IGNORE_FILE, "w"), indent=1)
    return sorted(cur)


# -------------------------------------------------------------- project kind
def detect_kind(folder: str) -> str:
    try:
        names = set(os.listdir(folder))
    except OSError:
        return "Other"

    def has(*f):
        return any(x in names for x in f)

    def ext(*e):
        return any(n.lower().endswith(e) for n in names)

    if has("package.json"):
        return "Node / JS"
    if has("requirements.txt", "setup.py", "pyproject.toml", "Pipfile") or ext(".py"):
        return "Python"
    if has("Cargo.toml"):
        return "Rust"
    if has("go.mod"):
        return "Go"
    if has("pom.xml", "build.gradle") or ext(".java"):
        return "Java"
    if has("index.html") or ext(".html"):
        return "Web"
    if has("Dockerfile", "docker-compose.yml"):
        return "Docker"
    if ext(".sh"):
        return "Shell"
    if ext(".ipynb"):
        return "Notebook"
    return "Other"


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
                      "html_url": r["html_url"], "pushed_at": r.get("pushed_at"),
                      "created_at": r.get("created_at"), "updated_at": r.get("updated_at")} for r in j)
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


def create_tag(token: str, owner: str, name: str, tag: str) -> dict:
    """Create a version tag on the repo's default branch (triggers the
    build-release workflow). Uses the user's PAT so the workflow actually runs."""
    if not tag.strip():
        return {"ok": False, "error": "empty tag"}
    c, repo = api("GET", f"/repos/{owner}/{name}", token)
    branch = repo.get("default_branch", "main") if c == 200 else "main"
    c, ref = api("GET", f"/repos/{owner}/{name}/git/ref/heads/{branch}", token)
    if c != 200:
        return {"ok": False, "error": f"could not read branch '{branch}': {ref.get('message')}"}
    sha = ref.get("object", {}).get("sha")
    c, j = api("POST", f"/repos/{owner}/{name}/git/refs", token,
               {"ref": f"refs/tags/{tag}", "sha": sha})
    if c in (200, 201):
        return {"ok": True, "tag": tag,
                "actions": f"https://github.com/{owner}/{name}/actions",
                "releases": f"https://github.com/{owner}/{name}/releases"}
    if c == 422:
        return {"ok": False, "error": f"tag '{tag}' already exists — use a new version"}
    return {"ok": False, "error": str(j.get("message"))}


def delete_repo(token: str, owner: str, name: str) -> dict:
    """Permanently delete a repository. Requires the token to have the
    'delete_repo' scope (the plain 'repo' scope does NOT include it)."""
    code, j = api("DELETE", f"/repos/{owner}/{name}", token)
    if code == 204:
        return {"ok": True}
    if code == 403:
        return {"ok": False, "error": "token lacks the 'delete_repo' scope — "
                "add it to your token at github.com/settings/tokens"}
    if code == 404:
        return {"ok": False, "error": "repo not found (already deleted?)"}
    return {"ok": False, "error": str(j.get("message") or f"HTTP {code}")}


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

    # init
    if not os.path.isdir(os.path.join(folder, ".git")):
        _run(["git", "init"], folder); log.append("git init")
    # ensure a committer identity exists (fresh git installs have none -> commit fails)
    ce, email = _run(["git", "config", "user.email"], folder)
    if ce != 0 or not email.strip():
        _run(["git", "config", "user.email", f"{login}@users.noreply.github.com"], folder)
        _run(["git", "config", "user.name", login], folder)
        log.append("set local git identity")
    # make sure we're on a 'main' branch
    _run(["git", "checkout", "-B", "main"], folder)
    _run(["git", "add", "-A"], folder)
    code, out = _run(["git", "commit", "-m", commit_msg], folder)
    # verify a commit actually exists (nothing to push otherwise)
    hc, _h = _run(["git", "rev-parse", "HEAD"], folder)
    if hc != 0:
        return {"ok": False, "error": "commit failed (no commit created): " + out, "html_url": html_url, "log": log}
    log.append("commit: " + (out.splitlines()[0] if out else "ok"))

    # remote: store a CLEAN url (no token) for the user's future git use
    _run(["git", "remote", "remove", "origin"], folder)
    _run(["git", "remote", "add", "origin", clone_url], folder)

    # push using a token-in-URL (the reliable way for GitHub over HTTPS).
    # The tokenized URL is only a transient argument — never written to
    # .git/config — and is masked in all logged output.
    push_url = f"https://x-access-token:{token}@github.com/{login}/{name}.git"
    code, out = _run(["git", "push", push_url, "main:main", "--force"], folder, token)
    if code == 0:
        # record the remote-tracking ref so change-detection works immediately
        _run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], folder)
        _run(["git", "branch", "--set-upstream-to=origin/main", "main"], folder)
    log.append("push: " + (out.splitlines()[-1] if out else "ok"))
    if code != 0:
        err = out
        if "workflow" in out and "scope" in out:
            err = ("this repo has a GitHub Actions workflow (.github/workflows/), so your "
                   "token needs the 'workflow' scope. Add it at github.com/settings/tokens "
                   "(keep 'repo' ticked), then reconnect and push again.")
        elif "Authentication" in out or "403" in out:
            err = ("authentication failed — your token may lack the 'repo' scope or has "
                   "expired. Recreate it at github.com/settings/tokens and reconnect.")
        return {"ok": False, "error": err, "html_url": html_url, "log": log}

    return {"ok": True, "html_url": html_url, "name": name, "private": private,
            "excluded_large": big, "log": log}


# -------------------------------------------------------------- author
def get_author() -> str:
    try:
        return open(AUTHOR_FILE).read().strip()
    except Exception:
        return ""


def save_author(name: str) -> str:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    open(AUTHOR_FILE, "w").write(name.strip())
    return name.strip()


# -------------------------------------------------------------- readme / license / release
def _has_file(folder: str, names: set[str]) -> bool:
    try:
        return any(f.lower() in names for f in os.listdir(folder))
    except OSError:
        return False


def has_readme(folder: str) -> bool:
    return _has_file(folder, {"readme.md", "readme", "readme.txt", "readme.rst", "readme.markdown"})


def has_license(folder: str) -> bool:
    return _has_file(folder, {"license", "license.md", "license.txt", "copying"})


def gen_readme(folder: str, force: bool = False) -> dict:
    folder = os.path.abspath(folder)
    if has_readme(folder) and not force:
        return {"ok": False, "error": "README already exists"}
    info = readme_gen.detect(folder)
    content = readme_gen.make_readme(os.path.basename(folder.rstrip("/")), folder, info)
    open(os.path.join(folder, "README.md"), "w", encoding="utf-8").write(content)
    return {"ok": True}


def gen_license(folder: str, author: str, force: bool = False) -> dict:
    folder = os.path.abspath(folder)
    if not author:
        return {"ok": False, "error": "set your name first"}
    if has_license(folder) and not force:
        return {"ok": False, "error": "LICENSE already exists"}
    year = datetime.date.today().year
    text = license_gen.APACHE.replace("{year}", str(year)).replace("{author}", author)
    open(os.path.join(folder, "LICENSE"), "w", encoding="utf-8").write(text)
    open(os.path.join(folder, "NOTICE"), "w", encoding="utf-8").write(
        f"Copyright {year} {author}\n\nLicensed under the Apache License, Version 2.0.\n")
    return {"ok": True}


_RELEASE_WORKFLOW = """name: Build & Release
on:
  push:
    tags: ["v*"]
  workflow_dispatch:
permissions:
  contents: write
jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-latest
            out: __APP__-linux
          - os: macos-latest
            out: __APP__-macos
          - os: windows-latest
            out: __APP__-windows.exe
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        shell: bash
        run: |
          python -m pip install --upgrade pip pyinstaller
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      - name: Build
        shell: bash
        run: pyinstaller --onefile --name __APP__ __ENTRY__
      - name: Name the artifact
        shell: bash
        run: |
          if [ "${{ runner.os }}" = "Windows" ]; then
            mv "dist/__APP__.exe" "dist/${{ matrix.out }}"
          else
            mv "dist/__APP__" "dist/${{ matrix.out }}"
          fi
      - uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.out }}
          path: dist/${{ matrix.out }}
  release:
    needs: build
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/')
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          path: dist
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/**/*
          generate_release_notes: true
"""


def detect_entry(folder: str) -> str:
    try:
        names = os.listdir(folder)
    except OSError:
        return "app.py"
    for c in ("app.py", "main.py", "run.py", "server.py", "manage.py", "cli.py"):
        if c in names:
            return c
    py = sorted(n for n in names if n.endswith(".py"))
    return py[0] if py else "app.py"


def add_release_workflow(folder: str, app_name: str = "", entry: str = "") -> dict:
    folder = os.path.abspath(folder)
    app_name = app_name or os.path.basename(folder.rstrip("/"))
    entry = entry or detect_entry(folder)
    wfdir = os.path.join(folder, ".github", "workflows")
    os.makedirs(wfdir, exist_ok=True)
    content = _RELEASE_WORKFLOW.replace("__APP__", app_name).replace("__ENTRY__", entry)
    open(os.path.join(wfdir, "build-release.yml"), "w", encoding="utf-8").write(content)
    return {"ok": True, "app": app_name, "entry": entry}


def scan_projects(root: str) -> list[dict]:
    """List immediate subfolders of `root` that look like projects."""
    root = os.path.abspath(os.path.expanduser(root))
    out = []
    if not os.path.isdir(root):
        return out
    ignored_set = set(load_ignored())
    for entry in sorted(os.listdir(root)):
        p = os.path.join(root, entry)
        if not os.path.isdir(p) or entry.startswith("."):
            continue
        is_git = os.path.isdir(os.path.join(p, ".git"))
        has_remote = dirty = ahead = no_upstream = False
        if is_git:
            _, rem = _run(["git", "remote", "-v"], p)
            has_remote = bool(rem.strip())
            _, st = _run(["git", "status", "--porcelain"], p)
            dirty = bool(st.strip())                         # uncommitted changes
            code, ab = _run(["git", "rev-list", "--count", "@{u}..HEAD"], p)
            ahead = (code == 0 and ab.strip() not in ("", "0"))  # committed but not pushed
        # "published" = a git repo with a remote, clean working tree, nothing unpushed
        published = is_git and has_remote and not dirty and not ahead
        changed_at = None       # epoch seconds of the most recent change
        changed_count = 0
        if dirty:
            lines = [l for l in st.splitlines() if l.strip()]
            changed_count = len(lines)
            newest = 0.0
            for l in lines:
                parts = l.split(None, 1)                      # status, path (strip-safe)
                rel = (parts[1] if len(parts) > 1 else "").strip().strip('"')
                if " -> " in rel:                            # renamed: "old -> new"
                    rel = rel.split(" -> ")[-1].strip().strip('"')
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(p, rel)))
                except OSError:
                    pass
            changed_at = newest or None
        elif ahead:
            c1, ts = _run(["git", "log", "-1", "--format=%ct"], p)   # last commit time
            if c1 == 0 and ts.strip().isdigit():
                changed_at = float(ts.strip())
            changed_count = int(ab.strip()) if ab.strip().isdigit() else 0
        if published:
            state = "published"
        elif is_git and (dirty or ahead):
            state = "changed"
        else:
            state = "new"
        out.append({"name": entry, "path": p, "is_git": is_git, "has_remote": has_remote,
                    "dirty": dirty, "ahead": ahead, "published": published, "state": state,
                    "changed_at": changed_at, "changed_count": changed_count,
                    "ignored": p in ignored_set, "kind": detect_kind(p),
                    "has_readme": has_readme(p), "has_license": has_license(p),
                    "has_release": os.path.isfile(os.path.join(p, ".github", "workflows", "build-release.yml"))})
    return out

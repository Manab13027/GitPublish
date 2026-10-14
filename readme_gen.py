#!/usr/bin/env python3
"""README generator — writes a tailored README.md into every project folder.

For each immediate subfolder it detects the stack, entry point, dependencies and
structure, and writes a README.md you can then refine (just fill the one-line
description). It never overwrites an existing README unless you pass --force, and
it skips folders whose names indicate offensive-security / malware tooling.

Usage:
  python3 readme_gen.py [ROOT] [--force] [--dry-run]
  (ROOT defaults to the folder this script lives in's parent, i.e. your
   Projects folder when readme_gen.py sits inside GitPublish/.)
"""
from __future__ import annotations
import json, os, re, sys

NOISE = {".git", "node_modules", ".venv", "venv", ".build-venv", "__pycache__",
         "dist", "build", ".idea", ".vscode", ".pytest_cache", ".DS_Store"}

# names that indicate malware / offensive tooling we won't auto-document
BLOCK = ["stealer", "keylog", "ransom", "botnet", "exploit", "cracker",
         "phish", "spoof", "ddos", "malware", "trojan", "backdoor", "grabber"]


def is_blocked(name: str) -> str | None:
    low = name.lower()
    for b in BLOCK:
        if b in low:
            return b
    return None


def pretty(name: str) -> str:
    s = re.sub(r"[-_]+", " ", name).strip()
    return s[:1].upper() + s[1:] if s else name


def read_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}


def detect(folder: str) -> dict:
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    nameset = set(names)
    has = lambda *f: any(x in nameset for x in f)
    ext = lambda *e: any(n.lower().endswith(e) for n in names)

    info = {"stack": "Other", "run": [], "deps": [], "desc": ""}

    pkg = read_json(os.path.join(folder, "package.json")) if "package.json" in nameset else {}

    if pkg:
        info["stack"] = "Node.js / JavaScript"
        info["desc"] = pkg.get("description", "")
        scripts = pkg.get("scripts", {})
        if "start" in scripts:
            info["run"] = ["npm install", "npm start"]
        elif "dev" in scripts:
            info["run"] = ["npm install", "npm run dev"]
        else:
            info["run"] = ["npm install"]
        deps = list((pkg.get("dependencies") or {}).keys())
        info["deps"] = deps[:12]
    elif has("manage.py"):
        info["stack"] = "Python (Django)"
        info["run"] = ["pip install -r requirements.txt", "python manage.py migrate", "python manage.py runserver"]
    elif has("requirements.txt", "setup.py", "pyproject.toml", "Pipfile") or ext(".py"):
        info["stack"] = "Python"
        entry = next((e for e in ("app.py", "main.py", "run.py", "server.py", "cli.py") if e in nameset), None)
        steps = []
        if "requirements.txt" in nameset:
            steps.append("pip install -r requirements.txt")
            try:
                info["deps"] = [l.strip() for l in open(os.path.join(folder, "requirements.txt"))
                                if l.strip() and not l.startswith("#")][:12]
            except Exception:
                pass
        steps.append(f"python {entry}" if entry else "python <entry>.py")
        info["run"] = steps
    elif has("Cargo.toml"):
        info["stack"] = "Rust"; info["run"] = ["cargo run"]
    elif has("go.mod"):
        info["stack"] = "Go"; info["run"] = ["go run ."]
    elif has("pom.xml", "build.gradle") or ext(".java"):
        info["stack"] = "Java"; info["run"] = ["# build with Maven/Gradle, then run the jar"]
    elif has("index.html") or ext(".html"):
        info["stack"] = "Static web"; info["run"] = ["# open index.html in a browser"]
    elif ext(".ipynb"):
        info["stack"] = "Jupyter notebook"; info["run"] = ["jupyter notebook"]
    elif ext(".sh"):
        info["stack"] = "Shell scripts"
        sh = next((n for n in ("run.sh", "start.sh", "setup.sh") if n in nameset), None)
        info["run"] = [f"./{sh}"] if sh else []

    if has("Dockerfile", "docker-compose.yml", "docker-compose.yaml"):
        info["run"] = info["run"] or ["docker compose up --build"]
    return info


def tree(folder: str, limit: int = 20) -> list[str]:
    try:
        entries = sorted(e for e in os.listdir(folder) if e not in NOISE and not e.startswith("."))
    except OSError:
        return []
    out = []
    for e in entries[:limit]:
        p = os.path.join(folder, e)
        out.append(f"{e}/" if os.path.isdir(p) else e)
    if len(entries) > limit:
        out.append(f"... (+{len(entries) - limit} more)")
    return out


def make_readme(name: str, folder: str, info: dict) -> str:
    title = pretty(name)
    desc = info["desc"].strip() or "_TODO: one line on what this project does and who it's for._"
    lines = [f"# {title}", "", desc, "", f"**Stack:** {info['stack']}", ""]

    if info["run"]:
        lines += ["## Getting started", "", "```bash", *info["run"], "```", ""]

    if info["deps"]:
        lines += ["## Dependencies", "", *[f"- `{d}`" for d in info["deps"]], ""]

    st = tree(folder)
    if st:
        lines += ["## Project structure", "", "```", *st, "```", ""]

    lines += ["## Notes", "",
              "_TODO: anything a new user should know — configuration, env vars, "
              "known limitations._", "",
              "---", "", f"_README scaffolded by readme_gen. Edit the TODOs to finish it._", ""]
    return "\n".join(lines)


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.expanduser(
        next((a for a in argv if not a.startswith("--")), os.path.dirname(here))))
    force = "--force" in argv
    dry = "--dry-run" in argv

    if not os.path.isdir(root):
        print(f"not a folder: {root}"); return
    print(f"Scanning {root}\n")

    made = skipped = blocked = existing = 0
    for entry in sorted(os.listdir(root)):
        p = os.path.join(root, entry)
        if not os.path.isdir(p) or entry.startswith(".") or entry in NOISE:
            continue
        b = is_blocked(entry)
        if b:
            print(f"  ⨯ skip   {entry}  (name suggests '{b}' tooling — not auto-documented)")
            blocked += 1
            continue
        # skip if ANY readme already exists (case-insensitive), unless --force
        try:
            existing_readme = next((f for f in os.listdir(p)
                                    if f.lower() in ("readme.md", "readme", "readme.txt",
                                                     "readme.rst", "readme.markdown")), None)
        except OSError:
            existing_readme = None
        if existing_readme and not force:
            print(f"  = keep   {entry}  ({existing_readme} already exists — left untouched)")
            existing += 1
            continue
        readme = os.path.join(p, "README.md")
        content = make_readme(entry, p, detect(p))
        if dry:
            print(f"  + would write  {entry}/README.md")
        else:
            open(readme, "w", encoding="utf-8").write(content)
            print(f"  + wrote  {entry}/README.md  [{detect(p)['stack']}]")
        made += 1

    print(f"\nDone. {made} written{' (dry run)' if dry else ''}, "
          f"{existing} already had one, {blocked} skipped as offensive tooling.")
    if blocked:
        print("If any skipped folder is actually a DEFENSIVE tool, rename it clearly "
              "or ask and it can be documented.")


if __name__ == "__main__":
    main(sys.argv[1:])

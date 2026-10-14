# GitPublish

Publish any project folder to **GitHub** as a repo, and flip private repos to
**public** — from a simple local dashboard or the command line. Zero
dependencies (Python 3.8+ and `git`), fully local. **Your GitHub token stays on
your machine** (a 0600 file at `~/.config/gitpublish/token`) and is only ever
sent to `api.github.com`. Tokens are never written into any repo or into
`.git/config`.

## 1. Get a GitHub token (one time)

Open <https://github.com/settings/tokens/new?scopes=repo&description=GitPublish>
and create a **classic** token with the **`repo`** scope. (A fine-grained token
also works — give it Repository access to *All repositories* with
**Administration** and **Contents** = Read/write. Administration is what lets it
flip private → public.)

Copy the token (starts with `ghp_` or `github_pat_`).

## 2A. Use the dashboard (recommended)

```bash
cd GitPublish
./run.sh                     # opens http://localhost:5060
# (point it elsewhere: PROJECTS_ROOT=~/code ./run.sh)
```

- Paste your token → **Connect**.
- **Your project folders** lists everything under your projects root. Hit
  **Publish** on any one (tick *private* first if you want it private).
- **Your GitHub repositories** lists all your repos with their visibility.
  Click **Make public** on any private one, or **Make ALL public** at the top.

## 2B. Or use the CLI

```bash
cd GitPublish
./ghpublish.py login ghp_your_token          # stores it locally
./ghpublish.py whoami
./ghpublish.py publish ~/Documents/Projects_Folder/Defender     # PUBLIC repo
./ghpublish.py publish ./MyApp --private --name my-app --desc "..."
./ghpublish.py list                          # all repos + visibility
./ghpublish.py make-public my-repo           # flip one private → public
./ghpublish.py make-public-all               # flip every private repo
./ghpublish.py batch ~/Documents/Projects_Folder   # publish each subfolder (public)
```

## What it does for you

- Creates the repo under your account (reuses it if the name already exists).
- Adds a sensible **`.gitignore`** if the folder doesn't have one
  (`node_modules`, `.venv`, `__pycache__`, build output, large media, secrets…).
- **Guards against GitHub's 100 MB file limit** — any oversized file is added to
  `.gitignore` and reported, so the push can't fail on size. (For large assets,
  use Git LFS or a release instead.)
- `git init` → commit → push to `main` with a one-shot auth header.

## Safety notes

- The token is read from `GH_TOKEN`/`GITHUB_TOKEN` env or the local 0600 file.
  It is masked in all output and never committed.
- Publishing is a **force push** to `main` of a fresh repo — intended for
  putting a project online the first time. For ongoing work, use normal `git`.
- `Make ALL public` changes visibility for every private repo you own; you'll be
  asked to confirm. It can't be auto-undone (re-privatising is per-repo on
  GitHub).

## Files

```
app.py                  local web server (stdlib http.server)
ghcore.py               GitHub API (urllib) + git ops + scanning
ghpublish.py            command-line interface
templates/dashboard.html the dashboard UI
run.sh                  launcher
```

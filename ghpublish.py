#!/usr/bin/env python3
"""GitPublish CLI — publish folders to GitHub and flip repos public.

Auth: set GH_TOKEN env var, or run `ghpublish.py login <TOKEN>` once
(stored 0600 in ~/.config/gitpublish/token).

Examples:
  ./ghpublish.py login ghp_xxx
  ./ghpublish.py whoami
  ./ghpublish.py list
  ./ghpublish.py publish ~/Documents/Projects_Folder/Defender          # public
  ./ghpublish.py publish ./MyApp --private --name my-app --desc "..."
  ./ghpublish.py make-public my-repo
  ./ghpublish.py make-public-all
  ./ghpublish.py batch ~/Documents/Projects_Folder                      # publish each subfolder (public)
"""
import sys, os
import ghcore as C


def need_token():
    t = C.get_token()
    if not t:
        print("No token. Run:  ghpublish.py login <YOUR_GITHUB_TOKEN>\n"
              "Create one at https://github.com/settings/tokens (scope: repo).")
        sys.exit(1)
    return t


def main(argv):
    if not argv:
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]

    if cmd == "login":
        if not rest:
            print("usage: ghpublish.py login <TOKEN>"); return
        C.save_token(rest[0])
        who = C.whoami(rest[0])
        print(f"saved token for: {who}" if who else "token saved, but GitHub rejected it — check scope (repo).")
        return

    if cmd == "whoami":
        print(C.whoami(need_token()) or "token invalid"); return

    if cmd == "list":
        t = need_token()
        for r in C.list_repos(t):
            vis = "private" if r["private"] else "public "
            print(f"  [{vis}] {r['full_name']}  {r['html_url']}")
        return

    if cmd == "publish":
        if not rest:
            print("usage: ghpublish.py publish <folder> [--private] [--name N] [--desc D]"); return
        folder = rest[0]
        private = "--private" in rest
        name = None; desc = ""
        if "--name" in rest: name = rest[rest.index("--name")+1]
        if "--desc" in rest: desc = rest[rest.index("--desc")+1]
        t = need_token()
        res = C.publish_folder(t, folder, name=name, private=private, desc=desc)
        for l in res["log"]: print("  " + l)
        if res["ok"]:
            print(f"\n✓ {'private' if private else 'PUBLIC'} repo ready: {res['html_url']}")
        else:
            print(f"\n✗ {res.get('error')}")
        return

    if cmd == "make-public":
        if not rest:
            print("usage: ghpublish.py make-public <repo-name>"); return
        t = need_token(); login = C.whoami(t)
        ok, j = C.set_visibility(t, login, rest[0], False)
        print(f"✓ {rest[0]} is now public" if ok else f"✗ {j.get('message')}")
        return

    if cmd == "make-public-all":
        t = need_token()
        res = C.make_all_public(t)
        if not res:
            print("No private repos found."); return
        for r in res:
            print(("✓ " if r["ok"] else "✗ ") + r["name"] + ("" if r["ok"] else f"  ({r['error']})"))
        print(f"\nFlipped {sum(1 for r in res if r['ok'])}/{len(res)} repos to public.")
        return

    if cmd == "batch":
        if not rest:
            print("usage: ghpublish.py batch <parent-folder> [--private]"); return
        parent = rest[0]; private = "--private" in rest
        t = need_token()
        for proj in C.scan_projects(parent):
            print(f"\n=== {proj['name']} ===")
            res = C.publish_folder(t, proj["path"], private=private)
            print(("  ✓ " + res["html_url"]) if res["ok"] else ("  ✗ " + str(res.get("error"))))
        return

    print(f"unknown command: {cmd}\n"); print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

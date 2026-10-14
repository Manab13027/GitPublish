# Building a standalone, signed, notarized GitPublish.app

This turns GitPublish into a **self-contained macOS app** — it bundles its own
Python, so users don't need Python installed, and once notarized it opens with
**no Gatekeeper warning** on any Mac. (`git` is still required on the target
machine, since GitPublish shells out to it.)

Everything here runs **on a Mac**. It can't be cross-built from Linux/Windows.

---

## A. Build only (free, works on your own machine)

```bash
cd ~/Documents/Projects_Folder/GitPublish
bash packaging/build_app.sh
```

Result: `dist/GitPublish.app`. Drag it to **/Applications**. First open on your
own Mac: right-click → **Open** → **Open** (once). Good enough if it's just for you.

To give it a custom icon, pass an `.icns`:
```bash
ICON=packaging/AppIcon.icns bash packaging/build_app.sh
```

---

## B. Signed + notarized (no warning, shareable)

### 1. Prerequisites (one time)
- An **Apple Developer account** ($99/year): <https://developer.apple.com/programs/>
- In **Xcode → Settings → Accounts**, add your Apple ID, then
  **Manage Certificates → + → Developer ID Application**. This installs a cert named
  `Developer ID Application: Your Name (TEAMID)` in your Keychain.
- Find its exact name:
  ```bash
  security find-identity -p codesigning -v
  ```

### 2. Store notarization credentials (one time)
Create an **app-specific password** at <https://appleid.apple.com> (Sign-In & Security
→ App-Specific Passwords), then:
```bash
xcrun notarytool store-credentials "GitPublishNotary" \
  --apple-id "you@example.com" \
  --team-id "TEAMID" \
  --password "the-app-specific-password"
```
`GitPublishNotary` is the profile name you'll pass to the build.

### 3. Build + sign + notarize
```bash
cd ~/Documents/Projects_Folder/GitPublish
DEV_ID="Developer ID Application: Your Name (TEAMID)" \
NOTARY_PROFILE="GitPublishNotary" \
bash packaging/build_app.sh
```

The script signs with the hardened runtime + entitlements, uploads to Apple,
waits for notarization, and staples the ticket. The resulting
`dist/GitPublish.app` opens cleanly on any Mac — drag it to /Applications or
share it (zip it first: `ditto -c -k --keepParent dist/GitPublish.app GitPublish.zip`).

---

## Notes
- **Updates:** rebuild and re-sign after you change the code — the binary is a
  snapshot, unlike the folder-based launcher which always runs the latest code.
- **Config/token** still live in `~/.config/gitpublish/` (outside the app), so
  they survive rebuilds.
- If notarization is rejected, run
  `xcrun notarytool log <submission-id> --keychain-profile GitPublishNotary`
  to see why (usually an unsigned nested binary — re-run; `--deep` handles most).

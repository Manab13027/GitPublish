// GitPublish — native macOS shell.
// Starts the bundled Python server (Contents/Resources/server/gitpublish-server)
// on a free localhost port and shows the dashboard in a WKWebView window.
// Built by packaging/build_app.sh with:  swiftc -O main.swift -o GitPublish
import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private var baseURL: URL!

    // MARK: lifecycle
    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()

        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()
        webView = WKWebView(frame: .zero, configuration: cfg)
        webView.uiDelegate = self
        webView.navigationDelegate = self
        webView.autoresizingMask = [.width, .height]
        if #available(macOS 13.3, *) { webView.isInspectable = true }  // right-click → Inspect Element

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1200, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "GitPublish"
        window.minSize = NSSize(width: 900, height: 600)
        window.backgroundColor = NSColor(red: 0x0d/255, green: 0x11/255, blue: 0x17/255, alpha: 1)
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("GitPublish")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        showMessage("Starting GitPublish…")
        startServer()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ n: Notification) { server?.terminate() }

    // MARK: server
    private func freePort() -> Int {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        defer { Darwin.close(fd) }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        addr.sin_port = 0
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, len) }
        }
        _ = withUnsafeMutablePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.getsockname(fd, $0, &len) }
        }
        return Int(UInt16(bigEndian: addr.sin_port))
    }

    private func startServer() {
        let exe = Bundle.main.resourceURL!.appendingPathComponent("server/gitpublish-server")
        guard FileManager.default.isExecutableFile(atPath: exe.path) else {
            return fail("The bundled server is missing:\n\(exe.path)\nRebuild with packaging/build_app.sh.")
        }
        let port = freePort()
        baseURL = URL(string: "http://127.0.0.1:\(port)/")!

        let logURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/GitPublish.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let log = try? FileHandle(forWritingTo: logURL)

        var env = ProcessInfo.processInfo.environment
        env["PORT"] = String(port)
        env["GITPUBLISH_NO_BROWSER"] = "1"
        env["GITPUBLISH_PARENT_PID"] = String(getpid())
        // Finder gives apps a bare PATH; include Homebrew so a brew git is found too.
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin")
        if env["SSL_CERT_FILE"] == nil, FileManager.default.fileExists(atPath: "/etc/ssl/cert.pem") {
            env["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"   // CA bundle for api.github.com
        }

        let p = Process()
        p.executableURL = exe
        p.environment = env
        p.standardOutput = log
        p.standardError = log
        p.terminationHandler = { [weak self] proc in
            DispatchQueue.main.async {
                guard let self = self, self.server != nil else { return }
                self.fail("The GitPublish server stopped (exit \(proc.terminationStatus)).\nSee ~/Library/Logs/GitPublish.log")
            }
        }
        do { try p.run() } catch { return fail("Could not start the server: \(error.localizedDescription)") }
        server = p
        waitForServer(attempt: 0)
    }

    private func waitForServer(attempt: Int) {
        var req = URLRequest(url: baseURL); req.timeoutInterval = 1
        URLSession.shared.dataTask(with: req) { [weak self] _, resp, _ in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if (resp as? HTTPURLResponse)?.statusCode == 200 {
                    self.webView.load(URLRequest(url: self.baseURL))
                } else if attempt < 100 {          // ~20 s
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.waitForServer(attempt: attempt + 1) }
                } else {
                    self.fail("The server didn't respond. See ~/Library/Logs/GitPublish.log")
                }
            }
        }.resume()
    }

    private func showMessage(_ text: String) {
        let esc = text.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: "\n", with: "<br>")
        webView.loadHTMLString("""
            <html><body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
            background:#0d1117;color:#8b949e;font:15px -apple-system;text-align:center;padding:40px">
            <div>\(esc)</div></body></html>
            """, baseURL: nil)
    }

    private func fail(_ msg: String) { server = nil; showMessage("⚠️ " + msg) }

    // MARK: links — keep the dashboard inside, send GitHub etc. to the browser
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = a.request.url, let host = u.host, host != "127.0.0.1",
           u.scheme == "http" || u.scheme == "https" {
            NSWorkspace.shared.open(u); return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration,
                 for a: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { NSWorkspace.shared.open(u) }   // target="_blank"
        return nil
    }

    // MARK: JS alert / confirm / prompt
    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage m: String,
                 initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = "GitPublish"; a.informativeText = m
        a.beginSheetModal(for: window) { _ in done() }
    }

    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage m: String,
                 initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = "GitPublish"; a.informativeText = m
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { done($0 == .alertFirstButtonReturn) }
    }

    func webView(_ w: WKWebView, runJavaScriptTextInputPanelWithPrompt p: String, defaultText d: String?,
                 initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping (String?) -> Void) {
        let a = NSAlert(); a.messageText = "GitPublish"; a.informativeText = p
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        field.stringValue = d ?? ""; a.accessoryView = field
        a.window.initialFirstResponder = field
        a.beginSheetModal(for: window) { done($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    // MARK: menu (Quit, Copy/Paste, Reload)
    @objc private func reload() { webView.reload() }

    private func buildMenu() {
        let main = NSMenu()
        func top(_ title: String, _ items: [NSMenuItem]) {
            let it = NSMenuItem(); let m = NSMenu(title: title)
            for i in items { m.addItem(i) }; it.submenu = m; main.addItem(it)
        }
        func item(_ t: String, _ s: Selector?, _ k: String, _ mods: NSEvent.ModifierFlags = .command) -> NSMenuItem {
            let i = NSMenuItem(title: t, action: s, keyEquivalent: k); i.keyEquivalentModifierMask = mods; return i
        }
        top("GitPublish", [
            item("About GitPublish", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            item("Hide GitPublish", #selector(NSApplication.hide(_:)), "h"),
            item("Quit GitPublish", #selector(NSApplication.terminate(_:)), "q"),
        ])
        top("Edit", [
            item("Undo", Selector(("undo:")), "z"),
            item("Redo", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("Cut", #selector(NSText.cut(_:)), "x"),
            item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Paste", #selector(NSText.paste(_:)), "v"),
            item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])
        let r = item("Reload", #selector(reload), "r"); r.target = self
        top("View", [r])
        top("Window", [
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Close", #selector(NSWindow.performClose(_:)), "w"),
        ])
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()

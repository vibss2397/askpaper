import AppKit
import WebKit

/// Owns the single persistent NSPanel + WKWebView (migration plan §6.2, §6.4).
/// Show/hide only — never destroy (D5: the transcript survives hide/show).
final class PanelController: NSObject, WKScriptMessageHandler, WKNavigationDelegate {

    static let panelWidth: CGFloat = 560
    static let panelHeight: CGFloat = 640

    private let baseURL: URL
    private var panel: KeyablePanel!
    private var webView: WKWebView!
    private var clickOutsideMonitor: Any?
    private var pendingCaptureID: String?
    /// Set by didFail, cleared by didFinish — show() retries the bare load so a
    /// cold start with the daemon down never leaves a white panel (§9.6).
    private var lastLoadFailed = false

    init(baseURL: URL) {
        self.baseURL = baseURL
        super.init()
        setupPanel()
    }

    // MARK: - lifecycle

    private func setupPanel() {
        let size = NSSize(width: Self.panelWidth, height: Self.panelHeight)
        let frame = NSRect(origin: .zero, size: size)

        let panel = KeyablePanel(
            contentRect: frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.isReleasedWhenClosed = false
        panel.hasShadow = true
        panel.backgroundColor = .clear
        panel.isMovable = false

        let content = NSView(frame: frame)

        let vibrancy = NSVisualEffectView(frame: frame)
        vibrancy.material = .hudWindow
        vibrancy.blendingMode = .behindWindow
        vibrancy.state = .active
        vibrancy.autoresizingMask = [.width, .height]
        content.addSubview(vibrancy)

        let config = WKWebViewConfiguration()
        // Non-persistent store: the page is a local, rapidly-iterated artifact of
        // the daemon — always fetch it fresh, never serve a stale cached copy
        // (WKWebView's disk cache aggressively serves old index.html otherwise).
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(self, name: "panel")
        // Pipe the page's console output + uncaught errors to stdout so page
        // bugs are debuggable from the app's log.
        let consoleScript = WKUserScript(source: """
        (() => {
          const send = (level, args) => {
            try {
              window.webkit.messageHandlers.panel.postMessage({ event: "console", level: level, text: args.map(String).join(" ") });
            } catch (e) {}
          };
          for (const level of ["log", "info", "warn", "error"]) {
            const orig = console[level].bind(console);
            console[level] = (...args) => { send(level, args); orig(...args); };
          }
        })();
        """, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        config.userContentController.addUserScript(consoleScript)
        let webView = WKWebView(frame: frame, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground") // page CSS composites over vibrancy
        webView.navigationDelegate = self
        content.addSubview(webView)

        panel.contentView = content
        self.panel = panel
        self.webView = webView

        // Preload /app so the first open is instant and the panel keeps state (D5).
        webView.load(URLRequest(url: appURL()))

        NotificationCenter.default.addObserver(
            self, selector: #selector(panelDidResignKey),
            name: NSWindow.didResignKeyNotification, object: panel
        )
        installDismissMonitors()
    }

    private func appURL(captureID: String? = nil) -> URL {
        var url = baseURL.appendingPathComponent("app")
        if let id = captureID {
            // The hash is client-side only; appending "#..." via URL fragments is
            // unreliable in Foundation, so build the string form directly.
            url = URL(string: baseURL.absoluteString + "/app#capture=" + id) ?? url
        }
        return url
    }

    // MARK: - show/hide

    var isVisible: Bool { panel.isVisible }
    var isKey: Bool { panel.isKeyWindow }

    /// Show the panel without reloading the page (transcript persists).
    /// If the last navigation failed (daemon was down), retry the load —
    /// the page owns all daemon-down UI, so a dead load must not persist.
    func show() {
        position()
        if lastLoadFailed && !webView.isLoading {
            print("[Panel] retrying bare load after earlier failure")
            lastLoadFailed = false
            webView.load(URLRequest(url: appURL()))
        }
        panel.makeKeyAndOrderFront(nil)
    }

    /// Show the panel after a capture handoff: load with #capture=<id> (D4).
    ///
    /// If the initial preload is still in flight, calling load() now would
    /// cancel it — and WebKit can then swallow the fragment navigation
    /// entirely (no hashchange, no init → the quote never renders). So when
    /// a load is in progress, defer ours until it finishes. A failed preload
    /// is not in flight, so the capture load doubles as the retry.
    func show(captureID: String) {
        position()
        if webView.isLoading {
            print("[Panel] load in flight — deferring capture reload \(captureID)")
            pendingCaptureID = captureID
        } else {
            lastLoadFailed = false
            loadCapture(captureID)
        }
        panel.makeKeyAndOrderFront(nil)
    }

    private func loadCapture(_ id: String) {
        print("[Panel] loading /app#capture=\(id)")
        webView.load(URLRequest(url: appURL(captureID: id)))
    }

    /// "New Thread" menu action: reload the bare page.
    func reload() {
        webView.load(URLRequest(url: appURL()))
        show()
    }

    func hide() {
        panel.orderOut(nil)
    }

    private func position() {
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first { $0.frame.contains(mouse) } ?? NSScreen.main
        let visible = screen?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let w = Self.panelWidth
        let h = min(Self.panelHeight, visible.height * 0.9) // never taller than the screen
        let x = visible.midX - w / 2
        let y = max(visible.maxY - visible.height * 0.15 - h, visible.minY)
        if panel.frame.size != NSSize(width: w, height: h) {
            panel.setContentSize(NSSize(width: w, height: h))
        }
        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    // MARK: - dismissal (Escape, click-outside, resignKey — §6.4)

    private func installDismissMonitors() {
        // Click-outside: a nonactivating panel never resigns key when another
        // app is clicked (its own app was never activated), so watch globally.
        // Escape is intentionally NOT intercepted natively: the page handles
        // it (close picker if open, else post "escape" via the panel message
        // handler) so in-page UI gets first crack at the key.
        clickOutsideMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown, .otherMouseDown]) { [weak self] _ in
            guard let self, self.panel.isVisible else { return }
            if !NSPointInRect(NSEvent.mouseLocation, self.panel.frame) {
                self.panel.orderOut(nil)
            }
        }
    }

    @objc private func panelDidResignKey() {
        // Covers cases the global monitor can't (e.g. app switching via ⌘Tab).
        if panel.isVisible {
            panel.orderOut(nil)
        }
    }

    // MARK: - WKNavigationDelegate (preload → capture-load sequencing)

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        print("[Panel] page loaded: \(webView.url?.absoluteString ?? "?")")
        lastLoadFailed = false
        if let id = pendingCaptureID {
            pendingCaptureID = nil
            loadCapture(id)
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        print("[Panel] page load FAILED: \(error.localizedDescription)")
        lastLoadFailed = true
        pendingCaptureID = nil
    }

    // MARK: - WKScriptMessageHandler (page → app messages)

    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard message.name == "panel" else { return }
        if let body = message.body as? String {
            if body == "escape" { hide() }
            return
        }
        if let dict = message.body as? [String: Any],
           dict["event"] as? String == "console" {
            let level = dict["level"] as? String ?? "log"
            print("[Page/\(level)] \(dict["text"] as? String ?? "")")
        }
    }
}

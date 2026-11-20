// WKWebView SSE-streaming probe (migration plan §6.5 risk gate).
// Loads the probe page (probe/probe.html, next to this file) into a real
// WKWebView with the daemon as baseURL — the page's /api/sse-probe fetch
// resolves to the daemon — and prints the page's verdict (inter-token
// arrival times for fetch + ReadableStream).
// Build & run (daemon must be up on :8765):
//   swiftc -framework AppKit -framework WebKit probe.swift -o /tmp/probe && /tmp/probe

import AppKit
import WebKit

let app = NSApplication.shared
let delegate = ProbeDelegate()
app.delegate = delegate

final class ProbeDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "probe")

        let w = NSWindow(
            contentRect: NSRect(x: 200, y: 200, width: 420, height: 240),
            styleMask: [.titled, .closable],
            backing: .buffered, defer: false
        )
        w.title = "PaperAgent WKWebView probe"
        self.webView = WKWebView(frame: .zero, configuration: config)
        w.contentView = webView
        self.window = w
        w.makeKeyAndOrderFront(nil)

        guard let html = try? String(contentsOf: URL(fileURLWithPath: "probe.html"), encoding: .utf8) else {
            print("PROBE-ERROR: probe.html not found next to probe.swift")
            NSApp.terminate(nil)
            return
        }
        // loadHTMLString + baseURL: the page's relative /api/sse-probe fetch
        // resolves to the daemon, same-origin, no served copy needed.
        webView.loadHTMLString(html, baseURL: URL(string: "http://localhost:8765/app/")!)

        // hard stop: probe page streams ~3 s; give it 20 s max
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) {
            print("PROBE-TIMEOUT")
            NSApp.terminate(nil)
        }
    }

    func userContentController(_ userContentController: WKUserContentController,
                              didReceive message: WKScriptMessage) {
        print("PROBE-RESULT: \(message.body)")
        NSApp.terminate(nil)
    }
}

app.setActivationPolicy(.regular)
app.run()

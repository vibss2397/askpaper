// Capture-flow probe (migration plan §6.5 harness, round 2).
// Loads the REAL page at /app#capture=<id> in a WKWebView with console piping,
// so the full capture → quote → resolve → renderAll path runs while stdout
// captures every page error. Build & run:
//   swiftc -framework AppKit -framework WebKit probe2.swift -o /tmp/probe2 && /tmp/probe2

import AppKit
import WebKit

let app = NSApplication.shared
let delegate = ProbeDelegate()
app.delegate = delegate

final class ProbeDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let captureID = (CommandLine.arguments.count > 1) ? CommandLine.arguments[1] : ""
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(self, name: "panel")
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

        let w = NSWindow(
            contentRect: NSRect(x: 200, y: 200, width: 600, height: 700),
            styleMask: [.titled, .closable],
            backing: .buffered, defer: false
        )
        w.title = "PaperAgent capture-flow probe"
        self.webView = WKWebView(frame: .zero, configuration: config)
        w.contentView = webView
        self.window = w
        w.makeKeyAndOrderFront(nil)

        var urlString = "http://localhost:8765/app"
        if !captureID.isEmpty { urlString += "#capture=" + captureID }
        webView.load(URLRequest(url: URL(string: urlString)!))

        DispatchQueue.main.asyncAfter(deadline: .now() + 12) {
            self.webView.evaluateJavaScript("""
            (() => {
              const b = document.getElementById("daemon-banner");
              const cs = getComputedStyle(b);
              return JSON.stringify({
                hiddenAttr: b.hidden,
                display: cs.display,
                visible: !b.hidden && cs.display !== "none",
                text: b.textContent.trim().slice(0, 60),
              });
            })()
            """) { result, _ in
                print("BANNER-CHECK: \(result ?? "nil")")
                print("PROBE-DONE")
                NSApp.terminate(nil)
            }
        }
    }

    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard message.name == "panel" else { return }
        if let dict = message.body as? [String: Any],
           dict["event"] as? String == "console" {
            let level = dict["level"] as? String ?? "log"
            print("[Page/\(level)] \(dict["text"] as? String ?? "")")
        }
    }
}

app.setActivationPolicy(.regular)
app.run()

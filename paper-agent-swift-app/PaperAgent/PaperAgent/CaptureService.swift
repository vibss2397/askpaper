import AppKit
import ApplicationServices
import CoreGraphics
import Darwin

struct CaptureResult {
    var selectedText = ""
    var sourceApp = ""
    var sourceTitle = ""
    var sourceURL = ""
    /// Apps whose Apple Events were denied by TCC (errAEEventNotPermitted -1743).
    var automationDenied: [String] = []
}

/// OS-level capture ladder (migration plan §6.3, hardened after real-world TCC friction).
///
/// Permission budget: ONLY Accessibility. AppleScript tab queries (which need per-app
/// Automation and get silently denied on modern macOS for ad-hoc apps) are now an
/// enhancement, not a dependency — every core step below works with Accessibility alone:
///   1. Frontmost app (no permission)
///   2. AX selected text on the system-wide focused element (editors, some web content)
///   3. AX window title (any app — including Firefox-based browsers like Zen)
///   4. URL: AppleScript tab queries when frontmost is a scriptable browser
///      → AX URL-bar walk (browser-agnostic) → arXiv-ID-from-title heuristic
///   5. Selection fallback: synthetic ⌘C posted to the frontmost process (CGEvent,
///      targeted, no activation) + pasteboard poll — the user's clipboard is restored
///      afterwards (the old System Events path is gone; so is its permission)
///
/// Unlike capture.ts (Raycast), browser scripts run ONLY when that browser is actually
/// frontmost: the nonactivating panel (D5) means frontmost is accurate at capture time,
/// and cross-app stale-tab queries produced only TCC noise.
final class CaptureService {

    /// Main-thread snapshot taken before dropping to a background queue.
    struct Context {
        var frontmostAppName: String
    }

    /// Browsers speaking the Chrome AppleScript tab suite.
    private static let chromeSuiteApps: Set<String> = [
        "Google Chrome", "Chromium", "Arc", "Brave Browser", "Microsoft Edge", "Opera", "Vivaldi",
    ]

    /// Apps the synthetic-⌘C clipboard fallback may target (§6.3 step 5 was
    /// browser-scoped for a reason: ⌘C into an arbitrary frontmost app can
    /// have non-copy side effects — terminals, games, design tools).
    private static let clipboardFallbackApps: Set<String> = Set([
        "Safari", "Preview", "Firefox", "Zen", "Skim",
    ]).union(chromeSuiteApps)

    private var automationDenied: [String] = []

    // MARK: - entry point

    func capture(context: Context, frontmostApp: NSRunningApplication?) -> CaptureResult {
        automationDenied = []
        let app = context.frontmostAppName
        print("[Capture] frontmost=\(app) axTrusted=\(Self.accessibilityGranted)")

        var source = Source(app: app, title: "", url: "")
        var selectedText = axSelectedText()?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        print("[Capture] AX selection: \(selectedText.isEmpty ? "none" : "\(selectedText.count) chars")")

        // Window title via AX — works for every app, no Automation needed.
        if let frontApp = frontmostApp, let title = axWindowTitle(of: frontApp) {
            source.title = title
            print("[Capture] AX window title: \(title.isEmpty ? "none" : "\"\(String(title.prefix(60)))\"")")
        }

        if let frontApp = frontmostApp {
            // URL attempt 1: AppleScript tab queries (needs Automation per browser).
            if app == "Safari" {
                if let s = safariURLTitle() {
                    source.url = s.url
                    if !s.title.isEmpty { source.title = s.title }
                }
                if selectedText.isEmpty, let js = runScript(Scripts.safariJSSelection, target: "Safari")?
                    .trimmingCharacters(in: .whitespacesAndNewlines), !js.isEmpty {
                    selectedText = js
                    print("[Capture] Safari JS selection: \(js.count) chars")
                }
            } else if Self.chromeSuiteApps.contains(app) {
                if let s = chromeSuiteURLTitle(appName: app) {
                    source.url = s.url
                    if !s.title.isEmpty { source.title = s.title }
                }
                if selectedText.isEmpty, let js = chromeSuiteJSSelection(appName: app)?
                    .trimmingCharacters(in: .whitespacesAndNewlines), !js.isEmpty {
                    selectedText = js
                    print("[Capture] \(app) JS selection: \(js.count) chars")
                }
            }

            // URL attempt 2: AX URL-bar walk (any browser, Accessibility only).
            if source.url.isEmpty, let v = axURLBarValue(of: frontApp), let normalized = Self.normalizedURL(v) {
                source.url = normalized
                print("[Capture] AX URL bar: \(normalized)")
            }

            // URL attempt 3: arXiv ID hiding in the window title (PDF tabs: "… - 2601.18795v2.pdf").
            if source.url.isEmpty, let id = Self.arxivID(in: source.title) {
                source.url = "https://arxiv.org/abs/\(id)"
                print("[Capture] arXiv ID from title: \(id)")
            }

            // Selection fallback: synthetic ⌘C + pasteboard, browser/PDF apps only.
            if selectedText.isEmpty, Self.clipboardFallbackApps.contains(app),
               let clip = clipboardSelection(of: frontApp) {
                selectedText = clip
                print("[Capture] clipboard selection: \(clip.count) chars")
            }
        }

        print("[Capture] result: sel=\(selectedText.isEmpty ? "0" : "\(selectedText.count)")c app=\(source.app) url=\(source.url.isEmpty ? "none" : source.url) denied=\(automationDenied)")
        return CaptureResult(
            selectedText: selectedText,
            sourceApp: source.app,
            sourceTitle: source.title,
            sourceURL: source.url,
            automationDenied: automationDenied
        )
    }

    private struct Source {
        var app: String
        var title: String
        var url: String
    }

    // MARK: - AX (Accessibility only)

    private func axSelectedText() -> String? {
        let systemWide = AXUIElementCreateSystemWide()
        var focusedRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            systemWide, kAXFocusedUIElementAttribute as CFString, &focusedRef
        ) == .success, let focusedValue = focusedRef else { return nil }
        let focused = focusedValue as! AXUIElement
        var textRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            focused, kAXSelectedTextAttribute as CFString, &textRef
        ) == .success else { return nil }
        return textRef as? String
    }

    private func axWindowTitle(of app: NSRunningApplication) -> String? {
        let el = AXUIElementCreateApplication(app.processIdentifier)
        for attribute in [kAXFocusedWindowAttribute, kAXMainWindowAttribute] {
            var winRef: CFTypeRef?
            guard AXUIElementCopyAttributeValue(el, attribute as CFString, &winRef) == .success,
                  let winValue = winRef else { continue }
            let window = winValue as! AXUIElement
            var titleRef: CFTypeRef?
            if AXUIElementCopyAttributeValue(window, kAXTitleAttribute as CFString, &titleRef) == .success,
               let title = titleRef as? String, !title.isEmpty {
                return title
            }
        }
        return nil
    }

    /// Depth-first walk of the frontmost window's AX tree, looking for a text field
    /// holding a URL (the browser address bar). Best-effort; Safari/Chromium/Firefox
    /// all expose the URL field as an AXTextField.
    private func axURLBarValue(of app: NSRunningApplication) -> String? {
        let el = AXUIElementCreateApplication(app.processIdentifier)
        var winRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, kAXFocusedWindowAttribute as CFString, &winRef) == .success,
              let winValue = winRef else { return nil }
        let window = winValue as! AXUIElement

        var found: String?
        var visited = 0

        func walk(_ node: AXUIElement, depth: Int) {
            guard found == nil, depth < 12, visited < 400 else { return }
            visited += 1
            var roleRef: CFTypeRef?
            if AXUIElementCopyAttributeValue(node, kAXRoleAttribute as CFString, &roleRef) == .success,
               (roleRef as? String) == "AXTextField" {
                var valRef: CFTypeRef?
                if AXUIElementCopyAttributeValue(node, kAXValueAttribute as CFString, &valRef) == .success,
                   let v = (valRef as? String)?.trimmingCharacters(in: .whitespaces),
                   Self.looksLikeURL(v) {
                    found = v
                    return
                }
            }
            var childrenRef: CFTypeRef?
            guard AXUIElementCopyAttributeValue(node, kAXChildrenAttribute as CFString, &childrenRef) == .success,
                  let children = childrenRef as! [AXUIElement]? else { return }
            for child in children {
                guard found == nil else { return }
                walk(child, depth: depth + 1)
            }
        }
        walk(window, depth: 0)
        return found
    }

    static func looksLikeURL(_ s: String) -> Bool {
        guard !s.isEmpty, !s.contains(" "), s.count < 2000 else { return false }
        if s.hasPrefix("http://") || s.hasPrefix("https://") { return true }
        return s.contains(".") && s.rangeOfCharacter(from: .letters) != nil
    }

    static func normalizedURL(_ raw: String) -> String? {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { return nil }
        if !s.contains("://") {
            s = (s.hasPrefix("localhost") ? "http://" : "https://") + s
        }
        return URL(string: s) != nil ? s : nil
    }

    /// Extracts an arXiv id (version stripped) from a title like
    /// "Reuse your FLOPs: … - 2601.18795v2.pdf".
    static func arxivID(in title: String) -> String? {
        guard let range = title.range(of: #"\b\d{4}\.\d{4,5}(v\d+)?\b"#, options: .regularExpression) else {
            return nil
        }
        var id = String(title[range])
        if let v = id.range(of: "v\\d+$", options: .regularExpression) {
            id.removeSubrange(v)
        }
        return id
    }

    // MARK: - clipboard fallback (CGEvent; replaces the System Events keystroke path)

    private func clipboardSelection(of app: NSRunningApplication) -> String? {
        let pasteboard = NSPasteboard.general
        let previousChangeCount = pasteboard.changeCount

        // Snapshot every pasteboard type as raw data so the restore is
        // faithful (images, RTF, file URLs — not just the plain string).
        var snapshot: [(NSPasteboard.PasteboardType, Data)] = []
        for type in pasteboard.types ?? [] {
            if let data = pasteboard.data(forType: type) { snapshot.append((type, data)) }
        }

        postCommandC(to: app.processIdentifier)

        // Poll for a fresh pasteboard write (replaces the fixed 0.3 s + 0.5 s retries).
        var captured: String?
        for _ in 0..<20 {
            usleep(30_000)
            if pasteboard.changeCount != previousChangeCount,
               let s = pasteboard.string(forType: .string)?
                   .trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty {
                captured = s
                break
            }
        }

        // Restore the user's clipboard (Phase 5 clobber fix). Only needed when
        // the target app actually wrote something (changeCount moved); a no-op
        // copy left the pasteboard untouched.
        if pasteboard.changeCount != previousChangeCount {
            pasteboard.clearContents()
            for (type, data) in snapshot {
                pasteboard.setData(data, forType: type)
            }
        }
        return captured
    }

    private func postCommandC(to pid: pid_t) {
        for keyDown in [true, false] {
            guard let event = CGEvent(keyboardEventSource: nil, virtualKey: 8 /* kVK_ANSI_C */, keyDown: keyDown) else {
                continue
            }
            event.flags = .maskCommand
            event.postToPid(pid)
            if keyDown { usleep(15_000) }
        }
    }

    // MARK: - AppleScript (enhancement path — needs per-app Automation)

    private func runScript(_ source: String, target: String) -> String? {
        // Cap the Apple Event wait: a hung/suspended target app would otherwise
        // block for the default (~60 s+) Apple Event timeout — on the main
        // thread (see below), freezing the whole app. Error -1712 flows through
        // the normal error path.
        let wrapped = "with timeout of 3 seconds\n" + source + "\nend timeout"
        // TCC prompts are only presentable when the Apple Event is sent from
        // the main thread; off-main (and especially from an LSUIElement app)
        // they are auto-denied (-1743) with no dialog ever shown — which also
        // means the app never appears under Privacy → Automation. Funnel every
        // Apple Event through the main queue so the prompt can render.
        if Thread.isMainThread {
            return runScriptOnMain(wrapped, target: target)
        }
        var result: String?
        DispatchQueue.main.sync {
            result = runScriptOnMain(wrapped, target: target)
        }
        return result
    }

    private func runScriptOnMain(_ source: String, target: String) -> String? {
        guard let script = NSAppleScript(source: source) else { return nil }
        var errorInfo: NSDictionary?
        let output = script.executeAndReturnError(&errorInfo)
        if let error = errorInfo {
            let number = (error[NSAppleScript.errorNumber] as? Int) ?? 0
            if number == -1743 { // errAEEventNotPermitted
                if !automationDenied.contains(target) { automationDenied.append(target) }
                print("[PaperAgent] Apple Events denied for \(target) — allow it in System Settings → Privacy → Automation (or ignore: the AX fallbacks cover it)")
            } else {
                print("[PaperAgent] AppleScript (\(target)) error \(number): \(error[NSAppleScript.errorMessage] ?? "unknown")")
            }
            return nil
        }
        return output.stringValue
    }

    private func chromeSuiteURLTitle(appName: String) -> (url: String, title: String)? {
        guard let url = runScript("tell application \"\(appName)\" to get URL of active tab of front window", target: appName) else {
            return nil
        }
        let title = runScript("tell application \"\(appName)\" to get title of active tab of front window", target: appName) ?? ""
        return (url, title)
    }

    private func chromeSuiteJSSelection(appName: String) -> String? {
        runScript("tell application \"\(appName)\" to execute front window's active tab javascript \"window.getSelection().toString()\"", target: appName)
    }

    private func safariURLTitle() -> (url: String, title: String)? {
        guard let url = runScript(Scripts.safariURL, target: "Safari") else { return nil }
        let title = runScript(Scripts.safariTitle, target: "Safari") ?? ""
        return (url, title)
    }

    // MARK: - Accessibility permission (§7.1)

    static var accessibilityGranted: Bool { AXIsProcessTrusted() }

    /// Puts up the system TCC prompt (with an "Open System Settings" button).
    static func promptForAccessibilityIfNeeded() {
        guard !AXIsProcessTrusted() else { return }
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        AXIsProcessTrustedWithOptions(options)
    }
}

private enum Scripts {
    static let safariURL = "tell application \"Safari\" to get URL of current tab of front window"
    static let safariTitle = "tell application \"Safari\" to get name of current tab of front window"
    static let safariJSSelection = "tell application \"Safari\" to do JavaScript \"window.getSelection().toString()\" in front document"
}

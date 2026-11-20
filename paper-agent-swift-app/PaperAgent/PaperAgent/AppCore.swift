import AppKit
import ApplicationServices
import Darwin

/// Central wiring (migration plan §6.2): owns the panel, health check, hotkey,
/// and the capture → handoff → show pipeline. Main-thread use only.
final class AppCore: ObservableObject {

    let baseURL: URL
    let panel: PanelController
    let health: HealthCheck

    private var hotkey: HotkeyCenter?
    private let handoff = HandoffService()

    /// Apps whose Automation permission is missing (drives the menu hint, §7.1).
    @Published private(set) var automationDenied: [String] = []

    /// Current global hotkey preset (Phase 5 hotkey configurability).
    @Published private(set) var hotkeyPreset: HotkeyPreset

    /// Apps whose only window is ordered out get App Napped: timers and network
    /// are suspended, which stalls health checks, the page's recovery poll and
    /// even mid-stream asks. Hold an activity assertion for the app's lifetime.
    private var antiNapToken: NSObjectProtocol?

    init() {
        // Always log to a file, regardless of launch method (Finder/open/terminal):
        // page-console piping and ladder diagnostics must be inspectable after the fact.
        let logPath = NSHomeDirectory() + "/Library/Logs/PaperAgent.log"
        // Rotate once at startup if the log grew past 1 MB (one .1 generation kept).
        let logURL = URL(fileURLWithPath: logPath)
        if let size = (try? logURL.resourceValues(forKeys: [.fileSizeKey]))?.fileSize, size > 1_000_000 {
            try? FileManager.default.removeItem(at: URL(fileURLWithPath: logPath + ".1"))
            try? FileManager.default.moveItem(at: logURL, to: URL(fileURLWithPath: logPath + ".1"))
        }
        if let handle = fopen(logPath, "a+") {
            setvbuf(handle, nil, _IONBF, 0)
            dup2(fileno(handle), STDOUT_FILENO)
            dup2(fileno(handle), STDERR_FILENO)
        }
        setvbuf(stdout, nil, _IONBF, 0)

        let urlString = UserDefaults.standard.string(forKey: "daemonUrl") ?? "http://localhost:8765"
        self.baseURL = URL(string: urlString) ?? URL(string: "http://localhost:8765")!
        self.panel = PanelController(baseURL: baseURL)
        self.health = HealthCheck(baseURL: baseURL)

        let presetID = UserDefaults.standard.string(forKey: "hotkeyPreset") ?? HotkeyPreset.defaultPreset.id
        self.hotkeyPreset = HotkeyPreset.byID(presetID)

        antiNapToken = ProcessInfo.processInfo.beginActivity(
            options: [.userInitiatedAllowingIdleSystemSleep],
            reason: "PaperAgent polls the daemon and streams answers; suspension breaks both"
        )

        health.start()

        // Bring the daemon up if it isn't running (daemon-lifecycle contract:
        // the LaunchAgent has no RunAtLoad — the PANEL is the trigger. KeepAlive
        // keeps it alive afterwards; a reboot requires one panel open.)
        DispatchQueue.global(qos: .utility).async { [baseURL] in
            guard !HealthCheck(baseURL: baseURL).isUp(timeout: 1.0) else { return } // up → nothing to do
            Self.kickstartDaemon()
            print("[AppCore] daemon was down — kickstarted LaunchAgent")
        }

        hotkey = HotkeyCenter(action: { [weak self] in
            self?.hotkeyPressed()
        }, preset: hotkeyPreset)
        hotkey?.start()
    }

    /// Starts the daemon via launchd (no-op if already running). Guarded by the
    /// health check above; a missing/uninstalled agent just fails harmlessly.
    static func kickstartDaemon() {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        proc.arguments = ["kickstart", "gui/\(getuid())/\(Self.daemonLabel)"]
        _ = try? proc.run()
    }

    static let daemonLabel = "com.vibhu.paperagent.daemon"

    // MARK: - hotkey settings

    func selectHotkey(_ preset: HotkeyPreset) {
        guard preset != hotkeyPreset else { return }
        hotkeyPreset = preset
        UserDefaults.standard.set(preset.id, forKey: "hotkeyPreset")
        hotkey?.rebind(to: preset)
    }

    // MARK: - menu actions

    func openPanel() {
        panel.show()
    }

    func newThread() {
        panel.reload()
    }

    func quit() {
        NSApp.terminate(nil)
    }

    // MARK: - hotkey (toggle: hide if shown+key, else capture → show — §6.4)

    /// Debounce: Carbon can fire twice for one chord (key-repeat, VM/keyboard
    /// quirks), and each pass runs the full capture ladder + a page reload.
    private static let hotkeyDebounceInterval: TimeInterval = 0.25
    private var lastHotkeyFire: TimeInterval = 0

    private func hotkeyPressed() {
        let now = CFAbsoluteTimeGetCurrent()
        guard now - lastHotkeyFire > Self.hotkeyDebounceInterval else {
            print("[Hotkey] debounced")
            return
        }
        lastHotkeyFire = now

        print("[Hotkey] pressed — panel visible=\(panel.isVisible) key=\(panel.isKey)")
        if panel.isVisible && panel.isKey {
            panel.hide()
            return
        }
        triggerCaptureAndShow()
    }

    /// Capture BEFORE the panel takes focus (§6.3 — Chrome PDF selection must
    /// survive). Snapshot what needs the main thread, then drop to background
    /// for AX + AppleScript + the POST, then show on main.
    func triggerCaptureAndShow() {
        let frontmost = NSWorkspace.shared.frontmostApplication
        let context = CaptureService.Context(
            frontmostAppName: frontmost?.localizedName ?? ""
        )

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }

            // Daemon down: show the panel immediately — the page renders its own
            // daemon-down state with recovery polling (§7.3, D8).
            guard self.health.isUp(timeout: 1.0) else {
                print("[Capture] daemon down — showing panel without handoff")
                DispatchQueue.main.async { self.panel.show() }
                return
            }

            let capture = CaptureService().capture(context: context, frontmostApp: frontmost)
            let captureID = self.handoff.postCapture(capture, baseURL: self.baseURL)
            print("[Capture] handoff id=\(captureID ?? "FAILED")")

            DispatchQueue.main.async {
                if !capture.automationDenied.isEmpty {
                    self.automationDenied = capture.automationDenied
                }
                if let id = captureID {
                    self.panel.show(captureID: id)
                } else {
                    self.panel.show()
                }
            }
        }
    }

    // MARK: - permissions (§7.1)

    var accessibilityGranted: Bool { CaptureService.accessibilityGranted }

    func grantAccessibility() {
        CaptureService.promptForAccessibilityIfNeeded()
        NSWorkspace.shared.open(
            URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
        )
    }

    func grantAutomation() {
        NSWorkspace.shared.open(
            URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")!
        )
    }
}

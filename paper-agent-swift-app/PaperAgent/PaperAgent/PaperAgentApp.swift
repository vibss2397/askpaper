import SwiftUI
import ApplicationServices

@main
struct PaperAgentApp: App {

    @StateObject private var core = AppCore()

    var body: some Scene {
        MenuBarExtra {            Button("Open Panel") { core.openPanel() }
                .keyboardShortcut(core.hotkeyPreset.displayKey, modifiers: core.hotkeyPreset.displayModifiers)
            Button("New Thread") { core.newThread() }

            Divider()

            Menu("Hotkey") {
                ForEach(HotkeyPreset.all) { preset in
                    Button(core.hotkeyPreset.id == preset.id ? "✓ \(preset.label)" : preset.label) {
                        core.selectHotkey(preset)
                    }
                }
            }

            Divider()

            if !core.accessibilityGranted {
                Button("Grant Accessibility…") { core.grantAccessibility() }
            }
            if !core.automationDenied.isEmpty {
                Button("Allow \(core.automationDenied.joined(separator: " & ")) Automation…") {
                    core.grantAutomation()
                }
            }

            Divider()

            Text(core.health.daemonUp
                 ? "Daemon: running at \(core.baseURL.host ?? "localhost")"
                   + (core.health.daemonVersion.isEmpty ? "" : " · v" + core.health.daemonVersion)
                   + (core.health.apiKeyPresent ? "" : " · NO API KEY (asks will fail)")
                 : "Daemon: unreachable")

            Divider()

            Button("Quit PaperAgent") { core.quit() }
                .keyboardShortcut("q", modifiers: [.command])
        } label: {
            Image(nsImage: MenuBarGlyph.image(up: core.health.daemonUp == true))
        }
        .menuBarExtraStyle(.menu)
    }
}

/// Menu-bar version of the app glyph ("talking stroke", left-facing), drawn as
/// a template image so the system tints it for light/dark menu bars; dimmed
/// while the daemon is unreachable (replaces the old plain status dot).
enum MenuBarGlyph {
    static func image(up: Bool) -> NSImage {
        let alpha: CGFloat = up ? 1 : 0.35
        let img = NSImage(size: NSSize(width: 36, height: 36), flipped: false) { _ in
            let k: CGFloat = 36.0 / 512.0
            let stroke = NSBezierPath()
            stroke.appendArc(withCenter: NSPoint(x: 274 * k, y: 256 * k), radius: 128 * k,
                             startAngle: 120, endAngle: 235, clockwise: true)
            stroke.move(to: NSPoint(x: 201 * k, y: 151 * k))
            stroke.curve(to: NSPoint(x: 92 * k, y: 208 * k),
                         controlPoint1: NSPoint(x: 160 * k, y: 108 * k),
                         controlPoint2: NSPoint(x: 110 * k, y: 132 * k))
            stroke.lineWidth = 2.6
            stroke.lineCapStyle = .round
            NSColor.black.withAlphaComponent(alpha).setStroke()
            stroke.stroke()
            NSColor.black.withAlphaComponent(alpha).setFill()
            NSBezierPath(ovalIn: NSRect(x: 68 * k, y: 232 * k, width: 36 * k, height: 36 * k)).fill()
            return true
        }
        img.isTemplate = true
        return img
    }
}

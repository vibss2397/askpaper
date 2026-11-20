import AppKit
import Carbon
import SwiftUI

/// Hotkey id constants live at file scope: the Carbon C callback cannot capture
/// the class's static members.
private let kHotKeySignature: OSType = 0x50414741 // 'PAGA'
private let kHotKeyEventID: UInt32 = 1

/// One selectable global-hotkey combo. Carbon masks for RegisterEventHotKey
/// plus SwiftUI equivalents for the menu's display shortcut.
struct HotkeyPreset: Equatable, Identifiable {
    let id: String
    let label: String
    let carbonModifiers: Int
    let keyCode: UInt32
    let displayKey: KeyEquivalent
    let displayModifiers: SwiftUI.EventModifiers

    static let all: [HotkeyPreset] = [
        // Bare-Cmd/Ctrl picks are chosen for low shadowing cost: a global
        // hotkey steals the combo system-wide, so the native bindings these
        // shadow (shell beginning-of-line for ⌃A; vestigial Stop for ⌘.;
        // Find-Next for ⌘G; Safari History for ⌘Y) are the least-missed.
        HotkeyPreset(id: "ctrl-a", label: "⌃A", carbonModifiers: controlKey,
                     keyCode: UInt32(kVK_ANSI_A), displayKey: "a", displayModifiers: .control),
        HotkeyPreset(id: "cmd-period", label: "⌘.", carbonModifiers: cmdKey,
                     keyCode: UInt32(kVK_ANSI_Period), displayKey: ".", displayModifiers: .command),
        HotkeyPreset(id: "cmd-g", label: "⌘G", carbonModifiers: cmdKey,
                     keyCode: UInt32(kVK_ANSI_G), displayKey: "g", displayModifiers: .command),
        HotkeyPreset(id: "cmd-y", label: "⌘Y", carbonModifiers: cmdKey,
                     keyCode: UInt32(kVK_ANSI_Y), displayKey: "y", displayModifiers: .command),
        // Post-cutover option: freed when the Raycast extension was removed.
        HotkeyPreset(id: "cmd-shift-p", label: "⌘⇧P", carbonModifiers: cmdKey | shiftKey,
                     keyCode: UInt32(kVK_ANSI_P), displayKey: "p", displayModifiers: [.command, .shift]),
    ]

    static let defaultPreset = HotkeyPreset.all[0]

    static func byID(_ id: String) -> HotkeyPreset {
        all.first { $0.id == id } ?? .defaultPreset
    }
}

/// Global hotkey via Carbon RegisterEventHotKey (migration plan §6.2, D6).
///
/// The combo is user-configurable (Phase 5 polish): AppCore persists a preset
/// id in UserDefaults and calls `rebind` on change — the Carbon event handler
/// survives rebinding since it is keyed on kHotKeyEventID, only the hotkey
/// ref is swapped.
final class HotkeyCenter {

    private let action: () -> Void
    private var hotKeyRef: EventHotKeyRef?
    private var eventHandler: EventHandlerRef?
    private var handlerInstalled = false
    private(set) var preset: HotkeyPreset

    init(action: @escaping () -> Void, preset: HotkeyPreset = .defaultPreset) {
        self.action = action
        self.preset = preset
    }

    func start() {
        register(preset)
    }

    /// Swaps the registered combo at runtime (hotkey configurability).
    func rebind(to newPreset: HotkeyPreset) {
        guard newPreset != preset else { return }
        if let ref = hotKeyRef {
            UnregisterEventHotKey(ref)
            hotKeyRef = nil
        }
        preset = newPreset
        register(newPreset)
    }

    private func register(_ combo: HotkeyPreset) {
        let id = EventHotKeyID(signature: kHotKeySignature, id: kHotKeyEventID)

        var ref: EventHotKeyRef?
        let status = RegisterEventHotKey(
            combo.keyCode,
            UInt32(combo.carbonModifiers),
            id,
            GetApplicationEventTarget(),
            0,
            &ref
        )
        guard status == noErr, ref != nil else {
            // Colliding registrations fail silently on macOS — always surface it (§7.2).
            print("[PaperAgent] hotkey registration FAILED for \(combo.label) (OSStatus \(status)) — is the combo taken?")
            return
        }
        hotKeyRef = ref
        print("[PaperAgent] hotkey registered: \(combo.label)")

        installHandlerIfNeeded()
    }

    private func installHandlerIfNeeded() {
        guard !handlerInstalled else { return }
        var spec = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        let callback: EventHandlerUPP = { _, event, userData in
            guard let userData else { return noErr }
            var hotKeyID = EventHotKeyID(signature: 0, id: 0)
            GetEventParameter(
                event,
                EventParamName(kEventParamDirectObject),
                EventParamType(typeEventHotKeyID),
                nil,
                MemoryLayout<EventHotKeyID>.size,
                nil,
                &hotKeyID
            )
            guard hotKeyID.id == kHotKeyEventID else { return noErr }
            let center = Unmanaged<HotkeyCenter>.fromOpaque(userData).takeUnretainedValue()
            center.fire()
            return noErr
        }
        let installStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            callback,
            1,
            &spec,
            Unmanaged.passUnretained(self).toOpaque(),
            &eventHandler
        )
        if installStatus != noErr {
            print("[PaperAgent] hotkey event handler install FAILED (OSStatus \(installStatus))")
        } else {
            handlerInstalled = true
        }
    }

    private func fire() {
        // Carbon hotkey events arrive on the main thread, but make it explicit.
        DispatchQueue.main.async { [action] in
            action()
        }
    }
}

import AppKit

/// Nonactivating, borderless panel that can still take keyboard focus for the
/// WKWebView (migration plan §6.4 / D5). One instance lives for the whole app
/// lifetime — it is only ever ordered out, never destroyed.
final class KeyablePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

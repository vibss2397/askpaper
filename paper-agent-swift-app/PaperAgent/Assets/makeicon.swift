import AppKit

// Generates PaperAgent.icns — the "talking stroke" glyph (left-facing:
// open jaw, voice flick, spoken-word dot) on a dark squircle.
// Usage: swift makeicon.swift  →  writes icon.iconset/ next to this file,
// then: iconutil -c icns icon.iconset -o ../Assets/PaperAgent.icns

let outDir = "icon.iconset"
try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

func render(_ px: Int) -> NSImage {
    let s = CGFloat(px)
    let img = NSImage(size: NSSize(width: s, height: s))
    img.lockFocus()
    let k = s / 512.0

    NSColor(calibratedRed: 0.10, green: 0.10, blue: 0.12, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 46 * k, y: 46 * k, width: 420 * k, height: 420 * k),
                 xRadius: 115 * k, yRadius: 115 * k).fill()

    let white = NSColor.white
    let stroke = NSBezierPath()
    // open circle (head), gap at lower-left (the open mouth)
    stroke.appendArc(withCenter: NSPoint(x: 274 * k, y: 256 * k), radius: 128 * k,
                     startAngle: 120, endAngle: 235, clockwise: true)
    // voice flick sweeping out of the mouth
    stroke.move(to: NSPoint(x: 201 * k, y: 151 * k))
    stroke.curve(to: NSPoint(x: 92 * k, y: 208 * k),
                 controlPoint1: NSPoint(x: 160 * k, y: 108 * k),
                 controlPoint2: NSPoint(x: 110 * k, y: 132 * k))
    stroke.lineWidth = 26 * k
    stroke.lineCapStyle = .round
    white.setStroke()
    stroke.stroke()
    // the word
    white.setFill()
    NSBezierPath(ovalIn: NSRect(x: 68 * k, y: 232 * k, width: 36 * k, height: 36 * k)).fill()

    img.unlockFocus()
    return img
}

func writePNG(_ px: Int, _ name: String) {
    let rep = NSBitmapImageRep(data: render(px).tiffRepresentation!)!
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: outDir + "/" + name))
}

writePNG(16, "icon_16x16.png")
writePNG(32, "icon_16x16@2x.png")
writePNG(32, "icon_32x32.png")
writePNG(64, "icon_32x32@2x.png")
writePNG(128, "icon_128x128.png")
writePNG(256, "icon_128x128@2x.png")
writePNG(256, "icon_256x256.png")
writePNG(512, "icon_256x256@2x.png")
writePNG(512, "icon_512x512.png")
writePNG(1024, "icon_512x512@2x.png")
print("iconset rendered")

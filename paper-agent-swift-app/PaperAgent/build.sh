#!/bin/sh
# Builds PaperAgent.app WITHOUT xcodebuild — only Command Line Tools are needed
# (the Xcode license is not required for swiftc). The sibling PaperAgent.xcodeproj
# remains the canonical project for the Xcode GUI once its license is accepted.
#
# Usage: ./build.sh   (from paper-agent-swift-app/PaperAgent/)
set -e
cd "$(dirname "$0")"

APP="build/PaperAgent.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

swiftc \
  -swift-version 5 \
  -parse-as-library \
  -o "$APP/Contents/MacOS/PaperAgent" \
  PaperAgent/*.swift

sed -e 's/\$(EXECUTABLE_NAME)/PaperAgent/' \
    -e 's/\$(PRODUCT_BUNDLE_IDENTIFIER)/com.vibhu.paperagent/' \
    -e 's/\$(PRODUCT_NAME)/PaperAgent/' \
    PaperAgent/Info.plist > "$APP/Contents/Info.plist"

# App icon (regenerate with: cd Assets && swift makeicon.swift && iconutil -c icns icon.iconset -o PaperAgent.icns)
cp Assets/PaperAgent.icns "$APP/Contents/Resources/"

# Sign with the stable self-signed identity when present (login keychain:
# "PaperAgent Signing") so TCC grants (Accessibility / Automation) survive
# rebuilds; fall back to ad-hoc, whose cdhash changes every build and
# silently invalidates prior grants (see migration plan §7.1).
IDENTITY=$(security find-identity -v -p codesigning | awk -F'"' '/PaperAgent Signing/{print $2; exit}')
if [ -n "$IDENTITY" ]; then
  codesign --force --sign "$IDENTITY" "$APP"
else
  echo "warning: 'PaperAgent Signing' identity not found — ad-hoc signing (TCC grants will not survive rebuilds)" >&2
  codesign --force --sign - "$APP"
fi

echo "Built $APP"

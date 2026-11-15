#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="${1:?App bundle path required}"
scratch="$(mktemp -d /tmp/ale-hud-build.XXXXXX)"
trap 'rm -rf "$scratch"' EXIT
sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
includes=(-IOverlay -IOverlay/Vendor -IOverlay/Vendor/headers -IOverlay/Vendor/KIF)
objects=()
for source in Overlay/Host.mm Overlay/Vendor/*.mm Overlay/Vendor/KIF/*.m; do
  object="$scratch/$(basename "$source").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios16.0 -isysroot "$sdk" \
    -fobjc-arc -fmodules -include Overlay/Prefix.h "${includes[@]}" -c "$source" -o "$object"
  objects+=("$object")
done
xcrun --sdk iphoneos swiftc -target arm64-apple-ios16.0 -sdk "$sdk" -swift-version 5 -O \
  -parse-as-library -module-name AleHUD -import-objc-header Overlay/Bridge.h \
  Shared/*.swift ImageRecognition/LocalOCR.swift Overlay/HUD.swift "${objects[@]}" \
  -Xlinker "$PWD/Overlay/Vendor/libraries/IOKit.tbd" -lc++ -framework UIKit -framework SwiftUI \
  -framework Vision -framework QuartzCore -o "$output/AleHUD"
chmod 755 "$output/AleHUD"
mkdir -p "$output/OverlayLicenses"
cp Overlay/Vendor/TrollSpeed-LICENSE "$output/OverlayLicenses/"
cp Overlay/Vendor/KIF/LICENSE "$output/OverlayLicenses/KIF-LICENSE"
cp Overlay/Vendor/KIF/Apache-2.0.txt "$output/OverlayLicenses/"
echo 'PASS: independent ARM64 HUD linked; device execution not implied'

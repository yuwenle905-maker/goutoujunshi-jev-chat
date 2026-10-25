#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v xcrun >/dev/null || { echo 'Requires Xcode with iPhoneOS SDK'; exit 1; }
mkdir -p build
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 \
  -fobjc-arc -fblocks -O2 -Wall -Wextra -Wno-unused-parameter \
  -dynamiclib -install_name '@rpath/GoutouAI.dylib' \
  ios/GTConfig.m ios/GTAdapter.m ios/GTCoordinator.m ios/GTUI.m \
  -framework Foundation -framework UIKit -framework Security \
  -o build/GoutouAI.dylib
codesign --force --sign - build/GoutouAI.dylib
file build/GoutouAI.dylib
otool -L build/GoutouAI.dylib
codesign --verify --strict build/GoutouAI.dylib
shasum -a 256 build/GoutouAI.dylib > build/SHA256SUMS.txt

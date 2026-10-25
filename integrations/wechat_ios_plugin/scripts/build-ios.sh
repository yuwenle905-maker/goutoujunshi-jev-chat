#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v xcrun >/dev/null || { echo 'Requires Xcode with iPhoneOS SDK'; exit 1; }
mkdir -p build
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 \
  -fobjc-arc -fblocks -fvisibility=hidden -O2 -Wall -Wextra -Wno-unused-parameter \
  -dynamiclib -install_name '@rpath/GoutouAI.dylib' \
  ios/GTConfig.m ios/GTAdapter.m ios/GTCoordinator.m ios/GTUI.m ios/GTBoot.c \
  -framework Foundation -framework UIKit -framework Security \
  -o build/GoutouAI.dylib
codesign --force --sign - build/GoutouAI.dylib
file build/GoutouAI.dylib
otool -L build/GoutouAI.dylib
codesign --verify --strict build/GoutouAI.dylib
xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 \
  -fvisibility=hidden -O2 -Wall -Wextra -dynamiclib \
  -install_name '@rpath/GoutouLoadProbe.dylib' ios/GTLoadProbe.c ios/GTBoot.c -o build/GoutouLoadProbe.dylib
codesign --force --sign - build/GoutouLoadProbe.dylib
codesign --verify --strict build/GoutouLoadProbe.dylib
otool -L build/GoutouLoadProbe.dylib
shasum -a 256 build/GoutouAI.dylib build/GoutouLoadProbe.dylib > build/SHA256SUMS.txt

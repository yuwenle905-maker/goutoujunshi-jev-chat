#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
xcodebuild -project GoutouJunshi.xcodeproj -scheme GoutouJunshi -configuration Debug \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath build-preview \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY= \
  GOUTOU_BUNDLE_ID=ai.ale.assistant GOUTOU_APP_GROUP=group.ai.ale.assistant \
  GOUTOU_KEYCHAIN_GROUP=GOUTOU00001.ai.ale.assistant build > /tmp/ale-preview-build.log 2>&1 || { tail -80 /tmp/ale-preview-build.log; exit 1; }
device=$(xcrun simctl list devices available -j | python3 -c 'import sys,json; a=json.load(sys.stdin); print(next(d["udid"] for ds in a["devices"].values() for d in ds if "iPhone" in d["name"] and d.get("isAvailable")))')
xcrun simctl boot "$device" || true
xcrun simctl bootstatus "$device" -b
xcrun simctl install "$device" build-preview/Build/Products/Debug-iphonesimulator/GoutouJunshi.app
mkdir -p build-trollstore/preview
xcrun simctl status_bar "$device" override --time '09:41' --batteryState charged --batteryLevel 100
xcrun simctl launch "$device" ai.ale.assistant --ale-preview
sleep 4
xcrun simctl io "$device" screenshot build-trollstore/preview/workspace-light.png
xcrun simctl ui "$device" appearance dark
sleep 2
xcrun simctl io "$device" screenshot build-trollstore/preview/workspace-dark.png
xcrun simctl ui "$device" content_size accessibility-large
sleep 2
xcrun simctl io "$device" screenshot build-trollstore/preview/workspace-large-text.png
xcrun simctl terminate "$device" ai.ale.assistant
xcrun simctl ui "$device" content_size large
xcrun simctl ui "$device" appearance light

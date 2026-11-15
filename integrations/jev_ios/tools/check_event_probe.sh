#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$PWD/build-event-probe"
mkdir -p "$output/AleEventProbe.app"
app="$output/AleEventProbe.app"
sdk="$(xcrun --sdk iphonesimulator --show-sdk-path)"
objects=()
for source in Tests/EventProbeHarness.m Overlay/EventProbe.mm Overlay/Vendor/TSEventFetcher.mm Overlay/Vendor/KIF/*.m; do
  object="$output/$(basename "$source").o"
  xcrun --sdk iphonesimulator clang -target arm64-apple-ios17.0-simulator -isysroot "$sdk" \
    -fobjc-arc -fmodules -include Overlay/Prefix.h -IOverlay -IOverlay/Vendor \
    -IOverlay/Vendor/headers -IOverlay/Vendor/KIF -c "$source" -o "$object"
  objects+=("$object")
done
xcrun --sdk iphonesimulator clang++ -target arm64-apple-ios17.0-simulator -isysroot "$sdk" \
  "${objects[@]}" -framework UIKit -framework Foundation \
  "$PWD/Overlay/Vendor/libraries/IOKit.Sim.tbd" -o "$app/AleEventProbe"
python3 - "$app/Info.plist" <<'PY'
import sys,plistlib
plistlib.dump(dict(CFBundleIdentifier='ai.ale.eventprobe',CFBundleExecutable='AleEventProbe',
 CFBundleName='AleEventProbe',CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1.0',
 MinimumOSVersion='17.0',LSRequiresIPhoneOS=True,UILaunchScreen={},UIDeviceFamily=[1]),open(sys.argv[1],'wb'))
PY
codesign --force --sign - "$app"
device=$(xcrun simctl list devices available -j | python3 -c 'import sys,json; d=[x for a in json.load(sys.stdin)["devices"].values() for x in a if x.get("isAvailable") and "iPhone" in x["name"]]; print(next((x["udid"] for x in d if x["state"]=="Booted"),d[0]["udid"]))')
xcrun simctl boot "$device" || true
python3 - "$device" <<'PY'
import subprocess,sys
subprocess.run(['xcrun','simctl','bootstatus',sys.argv[1],'-b'],check=True,timeout=180)
PY
xcrun simctl uninstall "$device" ai.ale.eventprobe || true
xcrun simctl install "$device" "$app"
xcrun simctl launch "$device" ai.ale.eventprobe
container=$(xcrun simctl get_app_container "$device" ai.ale.eventprobe data)
for attempt in {1..40}; do
  if [ -f "$container/Documents/event-probe.json" ]; then
    cp "$container/Documents/event-probe.json" "$output/result.json"
    xcrun simctl io "$device" screenshot "$output/result.png"
    python3 - "$output/result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1])); print(json.dumps(result,ensure_ascii=False))
assert result['passed'] and not result['window_became_key'], 'Production event source probe failed'
PY
    xcrun simctl terminate "$device" ai.ale.eventprobe
    echo 'PASS: actual production event source delivered a UIControl action and rejected the disabled control'
    exit 0
  fi
  sleep 1
done
echo 'FAIL: event probe did not finish; no pass result fabricated'
exit 1

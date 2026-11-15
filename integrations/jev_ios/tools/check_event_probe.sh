#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
bounded() {
  python3 - "$@" <<'PY'
import subprocess,sys
try:
    result=subprocess.run(sys.argv[2:],timeout=int(sys.argv[1])); sys.exit(result.returncode)
except subprocess.TimeoutExpired:
    print('Timed out: '+sys.argv[2],file=sys.stderr); sys.exit(124)
PY
}
output="$PWD/build-event-probe"
mkdir -p "$output/AleEventProbe.app"
app="$output/AleEventProbe.app"
sdk="$(xcrun --sdk iphonesimulator --show-sdk-path)"
objects=()
for source in Tests/EventProbeHarness.m Tests/TouchBurstProbe.mm Overlay/EventProbe.mm Overlay/TouchInput.mm Overlay/Vendor/HUDMainApplication.mm Overlay/Vendor/TSEventFetcher.mm Overlay/Vendor/KIF/*.m; do
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
device=$(bounded 30 xcrun simctl list devices available -j | python3 -c 'import sys,json; d=[x for a in json.load(sys.stdin)["devices"].values() for x in a if x.get("isAvailable") and "iPhone" in x["name"]]; print(next((x["udid"] for x in d if x["state"]=="Booted"),d[0]["udid"]))')
bounded 30 xcrun simctl boot "$device" || true
python3 - "$device" <<'PY'
import subprocess,sys
subprocess.run(['xcrun','simctl','bootstatus',sys.argv[1],'-b'],check=True,timeout=180)
PY
bounded 30 xcrun simctl uninstall "$device" ai.ale.eventprobe || true
bounded 60 xcrun simctl install "$device" "$app"
container=$(bounded 30 xcrun simctl get_app_container "$device" ai.ale.eventprobe data)
bounded 30 xcrun simctl launch "$device" ai.ale.eventprobe || true
for attempt in {1..40}; do
  if [ -f "$container/Documents/event-probe.json" ]; then
    cp "$container/Documents/event-probe.json" "$output/result.json"
    bounded 15 xcrun simctl io "$device" screenshot "$output/result.png" || true
    python3 - "$output/result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1])); print(json.dumps(result,ensure_ascii=False))
assert result['passed'] and result['native_sources_verified_before_sink'] and not result['window_became_key'], 'Production native-source / AX probe failed'
assert result['burst_routing']['passed'] and result['burst_routing']['rapid_tap_actions'] == 3 and result['burst_routing']['pan_moved_view'], 'Burst routing / pan failed'
PY
    bounded 15 xcrun simctl terminate "$device" ai.ale.eventprobe || true
    echo 'PASS: actual production event source delivered a UIControl action and rejected the disabled control'
    exit 0
  fi
  sleep 1
done
if [ -f "$container/Documents/event-progress.json" ]; then
  cp "$container/Documents/event-progress.json" "$output/result-progress.json"
  cat "$output/result-progress.json"
fi
echo 'FAIL: event probe did not finish; no pass result fabricated'
exit 1

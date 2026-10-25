#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/startup-tests
TEST_ROOT="$(pwd)/build/startup-tests/log-fixture"
mkdir -p "$TEST_ROOT/Library"
xcrun --sdk macosx clang -Iios -DGT_BOOT_TEST_ROOT="\"$TEST_ROOT\"" \
  ios/GTBoot.c tests/boot_test.c -o build/startup-tests/boot-test -Wall -Wextra
build/startup-tests/boot-test
SDK="$(xcrun --sdk iphonesimulator --show-sdk-path)"
ARCH="$(uname -m)"
APP="$(pwd)/build/startup-tests/GoutouSmokeHost.app"
mkdir -p "$APP/Frameworks"
xcrun --sdk iphonesimulator clang -target "$ARCH-apple-ios17.0-simulator" -isysroot "$SDK" \
  -fobjc-arc -fblocks -fvisibility=hidden -O1 -dynamiclib -install_name '@rpath/GoutouAI.dylib' \
  ios/GTConfig.m ios/GTAdapter.m ios/GTCoordinator.m ios/GTUI.m ios/GTBoot.c \
  -framework Foundation -framework UIKit -framework Security -o "$APP/Frameworks/GoutouAI.dylib"
xcrun --sdk iphonesimulator clang -target "$ARCH-apple-ios17.0-simulator" -isysroot "$SDK" \
  -fobjc-arc -fblocks tests/SmokeHost.m -framework Foundation -framework UIKit \
  -Wl,-needed_library,"$APP/Frameworks/GoutouAI.dylib" -Wl,-rpath,@executable_path/Frameworks -o "$APP/GoutouSmokeHost"
python3 - "$APP" <<'PY'
import plistlib,sys
from pathlib import Path
data=dict(CFBundleIdentifier='com.tencent.xin',CFBundleName='GoutouSmokeHost',CFBundleExecutable='GoutouSmokeHost',CFBundlePackageType='APPL',CFBundleShortVersionString='8.0.75',CFBundleVersion='smoke',MinimumOSVersion='17.0',LSRequiresIPhoneOS=True,UIDeviceFamily=[1,2],UILaunchScreen={})
with (Path(sys.argv[1])/'Info.plist').open('wb') as f:plistlib.dump(data,f)
PY
codesign --force --sign - "$APP/Frameworks/GoutouAI.dylib"
codesign --force --sign - "$APP"
xcrun simctl list devices available -j > build/startup-tests/devices.json
read -r DEVICE_ID WAS_BOOTED < <(python3 - <<'PY'
import json
d=json.load(open('build/startup-tests/devices.json'))
for runtime,devices in d['devices'].items():
    if '.iOS-' in runtime:
        for device in devices:
            if device.get('isAvailable') and 'iPhone' in device['name']:
                print(device['udid'],int(device['state']=='Booted'));raise SystemExit
raise SystemExit('No available iPhone simulator')
PY
)
cleanup() {
  xcrun simctl terminate "$DEVICE_ID" com.tencent.xin 2>/dev/null || true
  if [ "$WAS_BOOTED" = 0 ]; then xcrun simctl shutdown "$DEVICE_ID" 2>/dev/null || true; fi
}
trap cleanup EXIT
if [ "$WAS_BOOTED" = 0 ]; then xcrun simctl boot "$DEVICE_ID"; fi
xcrun simctl bootstatus "$DEVICE_ID" -b
xcrun simctl install "$DEVICE_ID" "$APP"
xcrun simctl launch "$DEVICE_ID" com.tencent.xin
CONTAINER="$(xcrun simctl get_app_container "$DEVICE_ID" com.tencent.xin data)"
for _ in $(seq 1 30); do
  if [ -f "$CONTAINER/Documents/goutou-smoke-result.json" ]; then break; fi
  sleep 1
done
cp "$CONTAINER/Documents/goutou-smoke-result.json" build/startup-tests/result.json
cp "$CONTAINER/Library/Logs/GoutouAI-boot.log" build/startup-tests/boot.log
python3 - <<'PY'
import json
d=json.load(open('build/startup-tests/result.json'))
assert d.get('public_shortcut_count')==1,d
# Boxed Objective-C comparison expressions serialize as NSNumber 0/1 on some SDKs.
for key in ['startup_survived','private_hook_absent_until_opt_in','namespaced_settings_class_present','private_hook_installed_after_opt_in','repeat_enable_does_not_rehook','original_receive_called_once','settings_ui_constructed']:
    assert type(d.get(key)) in (bool,int) and d[key] == 1,(key,d)
assert not d.get('exception'),d
print(json.dumps(d,indent=2))
PY

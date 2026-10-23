#!/usr/bin/env python3
"""Package device builds for TrollStore, preserving sandbox and shared groups.

No Apple account, provisioning profile, API key or private entitlement is needed.
This validates packaging, not keyboard behavior on a physical device.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile


def read_info(bundle):
    with (bundle / "Info.plist").open("rb") as stream:
        return plistlib.load(stream)


def check_bundle(bundle, expected_id, app_group, keychain_group):
    info = read_info(bundle)
    assert info["CFBundleIdentifier"] == expected_id, f"Unexpected bundle ID: {bundle}"
    assert info["GoutouAppGroup"] == app_group, f"App Group mismatch: {bundle}"
    assert info["GoutouKeychainGroup"] == keychain_group, f"Keychain mismatch: {bundle}"
    assert info["CFBundleSupportedPlatforms"] == ["iPhoneOS"], "Simulator build cannot be installed"
    minimum = tuple(map(int, info["MinimumOSVersion"].split(".")))
    assert minimum <= (17, 0), f"Requires newer iOS: {minimum}"
    executable = bundle / info["CFBundleExecutable"]
    assert executable.is_file(), f"Missing executable: {executable}"
    archs = subprocess.check_output(["lipo", "-archs", str(executable)], text=True).strip()
    assert archs == "arm64", f"Expected ARM64 device executable, got {archs}"
    return info, executable


def entitlements_for(identifier, app_group, keychain_group, capture=False):
    entitlements = {
        "application-identifier": "GOUTOU00001." + identifier,
        "com.apple.security.application-groups": [app_group],
    }
    if not capture:
        entitlements["keychain-access-groups"] = [keychain_group]
    return entitlements


def main():
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    identifier = os.environ["GOUTOU_BUNDLE_ID"]
    app_group = os.environ["GOUTOU_APP_GROUP"]
    keychain_group = os.environ["GOUTOU_KEYCHAIN_GROUP"]
    output.mkdir(parents=True, exist_ok=True)
    ldid = shutil.which("ldid")
    assert ldid, "Install ldid first"
    with tempfile.TemporaryDirectory(prefix="goutou-trollstore-") as scratch:
        root = Path(scratch)
        payload = root / "Payload"
        payload.mkdir()
        app = payload / source.name
        shutil.copytree(source, app, symlinks=True)
        targets = [
            (app / "PlugIns/GoutouKeyboard.appex", identifier + ".keyboard", False),
            (app / "PlugIns/GoutouCapture.appex", identifier + ".capture", True),
            (app, identifier, False),
        ]
        assert set(p.name for p in (app / "PlugIns").glob("*.appex")) == {
            "GoutouKeyboard.appex", "GoutouCapture.appex"
        }, "Both keyboard and capture extensions must be embedded"
        manifest = []
        for index, (bundle, bundle_id, capture) in enumerate(targets):
            info, executable = check_bundle(bundle, bundle_id, app_group, keychain_group)
            expected = entitlements_for(bundle_id, app_group, keychain_group, capture)
            entitlement_file = root / f"entitlements-{index}.plist"
            entitlement_file.write_bytes(plistlib.dumps(expected))
            subprocess.run([ldid, "-S" + str(entitlement_file), str(executable)], check=True)
            actual = plistlib.loads(subprocess.check_output([ldid, "-e", str(executable)]))
            assert actual == expected, f"Entitlement verification failed: {bundle_id}"
            executable.chmod(executable.stat().st_mode | 0o111)
            manifest.append({"bundle_id": bundle_id, "minimum_ios": info["MinimumOSVersion"],
                             "architecture": "arm64", "entitlements": actual})
        ipa = output / "GoutouJunshi-TrollStore.ipa"
        # ditto preserves executable permissions and bundle structure on macOS.
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(payload), str(ipa)], check=True)
        with zipfile.ZipFile(ipa) as archive:
            assert archive.testzip() is None, "IPA CRC validation failed"
            for bundle, _, _ in targets:
                executable = bundle / read_info(bundle)["CFBundleExecutable"]
                entry = archive.getinfo(executable.relative_to(root).as_posix())
                assert (entry.external_attr >> 16) & 0o111, "Executable permissions missing"
        with ipa.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        (output / "SHA256SUMS.txt").write_text(f"{digest}  {ipa.name}\n", encoding="utf-8")
        (output / "build-info.json").write_text(json.dumps({
            "commit": os.environ.get("GITHUB_SHA", "local"), "targets": manifest,
            "installation": "TrollStore", "device_validation": "pending",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Verified IPA: {ipa.name}; SHA256: {digest}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Winbox URL protocol handler setup for macOS.
Creates a .app bundle that handles winbox:// URLs from Cf Control.

On modern macOS (Sequoia+), Launch Services requires a Mach-O binary
(not a shell script) as the app executable to register URL schemes.
This script compiles a small Swift helper that receives the URL event
via NSAppleEventManager and launches WinBox with parsed arguments.

Usage: python3 winbox.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME = "WinboxHandler"
APP_DIR = Path.home() / "Applications" / f"{APP_NAME}.app"
DEFAULT_WINBOX = Path("/Applications/WinBox.app/Contents/MacOS/WinBox")
# ──────────────────────────────────────────────────────────────────────────────

INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>cz.cfcontrol.winbox-handler</string>
    <key>CFBundleName</key>
    <string>{app_name}</string>
    <key>CFBundleDisplayName</key>
    <string>Winbox URL Handler</string>
    <key>CFBundleExecutable</key>
    <string>WinboxHandler</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>2.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key>
            <string>Winbox Protocol</string>
            <key>CFBundleURLSchemes</key>
            <array>
                <string>winbox</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
"""

# Swift source for the URL handler binary.
# Registers for Apple Events (GetURL), parses the winbox:// URL,
# and launches the WinBox binary with the extracted arguments.
SWIFT_SOURCE = """\
import Cocoa

let winboxPath = "{winbox_path}"

class AppDelegate: NSObject, NSApplicationDelegate {{
    func applicationWillFinishLaunching(_ notification: Notification) {{
        NSAppleEventManager.shared().setEventHandler(
            self,
            andSelector: #selector(handleGetURL(event:reply:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL)
        )
    }}

    @objc func handleGetURL(event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) {{
        guard let urlString = event.paramDescriptor(forKeyword: keyDirectObject)?.stringValue else {{
            showAlert("No URL received.")
            NSApp.terminate(nil)
            return
        }}

        // Strip scheme — handle both winbox:// and winbox:/
        var params = urlString
        if params.hasPrefix("winbox://") {{
            params = String(params.dropFirst("winbox://".count))
        }} else if params.hasPrefix("winbox:/") {{
            params = String(params.dropFirst("winbox:/".count))
        }}

        // Strip trailing slash
        if params.hasSuffix("/") {{
            params = String(params.dropLast())
        }}

        let parts = params.split(separator: "/", maxSplits: 2).map(String.init)

        guard let ip = parts.first, !ip.isEmpty else {{
            showAlert("Could not parse IP from URL: \\(urlString)")
            NSApp.terminate(nil)
            return
        }}

        var args = [ip]
        if parts.count > 1 {{ args.append(parts[1]) }}
        if parts.count > 2 {{ args.append(parts[2]) }}

        let process = Process()
        process.executableURL = URL(fileURLWithPath: winboxPath)
        process.arguments = args
        do {{
            try process.run()
        }} catch {{
            showAlert("Failed to launch WinBox: \\(error.localizedDescription)")
        }}

        // Give WinBox a moment to start, then quit
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {{
            NSApp.terminate(nil)
        }}
    }}

    func showAlert(_ message: String) {{
        let alert = NSAlert()
        alert.messageText = "WinboxHandler"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
    }}
}}

let delegate = AppDelegate()
NSApplication.shared.delegate = delegate
NSApp.run()
"""


def find_winbox() -> Path:
    candidates = [
        DEFAULT_WINBOX,
        Path("/Applications/winbox"),
        Path("/usr/local/bin/winbox"),
        Path.home() / "Downloads" / "winbox",
    ]
    for p in candidates:
        if p.exists():
            return p

    result = subprocess.run(
        [
            "osascript",
            "-e",
            'POSIX path of (choose file with prompt "Select your Winbox binary:" '
            "default location (path to applications folder))",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())

    print("Winbox binary not found. Set DEFAULT_WINBOX in this script manually.")
    sys.exit(1)


def create_app(winbox_path: Path) -> None:
    # Clean previous bundle
    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)

    contents = APP_DIR / "Contents"
    macos_dir = contents / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    # Info.plist
    (contents / "Info.plist").write_text(INFO_PLIST.format(app_name=APP_NAME))

    # Write Swift source to a temp file and compile
    swift_file = macos_dir / "main.swift"
    swift_file.write_text(SWIFT_SOURCE.format(winbox_path=winbox_path))

    binary = macos_dir / APP_NAME
    result = subprocess.run(
        ["swiftc", "-o", str(binary), str(swift_file), "-framework", "Cocoa"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Swift compilation failed:\n{result.stderr}")
        sys.exit(1)

    # Remove source file — only the binary is needed
    swift_file.unlink()

    print(f"App bundle created: {APP_DIR}")


def sign_app() -> None:
    """Ad-hoc sign the app bundle."""
    result = subprocess.run(
        ["codesign", "--force", "--sign", "-", str(APP_DIR)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("Ad-hoc signed.")
    else:
        print(f"Signing failed (non-fatal): {result.stderr}")


def register() -> None:
    """Re-register the app with Launch Services so macOS picks up the URL scheme."""
    lsregister = Path(
        "/System/Library/Frameworks/CoreServices.framework"
        "/Versions/A/Frameworks/LaunchServices.framework"
        "/Versions/A/Support/lsregister"
    )
    if lsregister.exists():
        subprocess.run([str(lsregister), "-f", str(APP_DIR)], check=True)
        print("Registered with Launch Services.")
    else:
        print("lsregister not found – log out/in once to activate the URL scheme.")


def test_url() -> None:
    url = "winbox://192.168.88.1/admin/password"
    print(f"\nTest with: open '{url}'")
    ans = input("Run test now? [y/N] ").strip().lower()
    if ans == "y":
        subprocess.run(["open", url])


if __name__ == "__main__":
    print(f"Setting up {APP_NAME}.app in ~/Applications …\n")
    winbox = find_winbox()
    print(f"Using Winbox binary: {winbox}")
    create_app(winbox)
    sign_app()
    register()
    print("\nDone! The winbox:// protocol is now registered.")
    test_url()

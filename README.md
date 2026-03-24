# winbox-url-handler

Register the `winbox://` URL scheme on macOS so that clicking links like `winbox://10.0.0.1/admin/password` in a web-based network management system opens [MikroTik WinBox](https://mikrotik.com/download/winbox) with the correct address, username, and password pre-filled.

## URL format

```
winbox://<address>[:<port>]/<username>/<password>
```

Example:
- `winbox://192.168.88.1/admin/secret`

## Prerequisites

- **macOS 12+** (Monterey or later; tested on Sequoia)
- **Python 3** (included with macOS)
- **Xcode Command Line Tools** — needed for the Swift compiler (`swiftc`).
  Install with:
  ```bash
  xcode-select --install
  ```
- **WinBox** — download from https://mikrotik.com/download/winbox and install to `/Applications`.

## Installation

```bash
python3 winbox.py
```

The script will:

1. Locate your WinBox installation (checks `/Applications/WinBox.app` first; if not found, opens a file picker).
2. Compile a small native Swift helper app into `~/Applications/WinboxHandler.app`.
3. Ad-hoc sign the app bundle.
4. Register the `winbox://` URL scheme with macOS Launch Services.

After that, any `winbox://` link in your browser will open WinBox.

## Uninstall

```bash
rm -rf ~/Applications/WinboxHandler.app
```

Then log out and back in (or restart) to clear the URL scheme registration.

## How it works

On modern macOS (Sequoia+), Launch Services only registers URL scheme handlers from app bundles with a proper Mach-O binary — shell scripts won't work. This tool compiles a minimal Swift/Cocoa app that:

1. Listens for `GetURL` Apple Events from the OS.
2. Parses the `winbox://` URL into address, username, and password.
3. Launches WinBox with the parsed arguments.
4. Quits itself after handing off to WinBox.

## License

MIT

# Drishya

Image descriptions for NVDA using **SmolVLM2 500M**. Describe the screen, current
focus or navigator object, then review or copy the result.

Created and maintained by **Aakash**. Free and open source under GPL-2.0-or-later.

## Installation

1. [Download Drishya 0.2.0](https://github.com/beyondsighttech/drishya/releases/download/v0.2.0/drishya-0.2.0.nvda-addon), open the file to install it, and restart NVDA.
2. If the model is missing, Drishya offers **Download** or **Later**.
3. Choose Download for the one-time, approximately **662 MB** model/runtime
   download. Settings shows progress and allows cancellation.
4. After installation, descriptions work offline. No GPU, separate Python,
   Ollama or external API key is required.

The release package is small. Only SmolVLM2 and its CPU runtime are downloaded;
weights are checksum-verified and stored in NVDA's configuration directory.
If you choose Later, download from Settings whenever convenient. Attempting a
description without the model also offers the download.

## Commands

- **NVDA+Shift+I:** open the description menu; use arrows and Enter.
- **Entire screen / Current focus / Navigator object:** choose the target.
- **Alt+C:** copy. **Alt+D:** review description. **Alt+R:** retry the snapshot.
- **Escape:** close/cancel. **Last description:** reopen the recent result.
- **Settings:** available in the menu and NVDA's Tools menu.

Settings provides detail, image size, CPU threads and automatic reading.
**Alt+M** downloads/verifies the model; **Alt+S** saves. Defaults: concise,
1024 pixels and four CPU threads. Smaller inputs can be faster and lose details.

## Screen Curtain

Windows Graphics Capture is used when the installed NVDA build supports it. This
can capture while Screen Curtain stays on; Drishya never disables it automatically.
If WGC is unavailable or fails while the curtain is enabled, a clear message asks
you to disable the curtain and retry. The menu and Settings remain accessible.

## Compatibility and privacy

Windows x64, NVDA **2026.1+**; current API target 2026.3.1. WGC is detected at
runtime because NVDA's capture helper is internal and may change. Older builds
use GDI with Screen Curtain off. English descriptions are supported.

Images stay on this computer and are not uploaded to an inference service.
Captures are discarded when the result closes. The last description is held in
memory until settings change, the session locks or NVDA exits. Copy writes text
to the clipboard. Models can miss details or invent text/objects; quantization
and resizing are not guaranteed lossless.

Missing/corrupt files: choose Download / verify model. Timeouts: reduce image size.
Clipboard busy: retry Copy. Shortcut conflicts: use NVDA Input Gestures.

## Development

Python 3.13; development dependencies: pytest, wxPython and Pillow.

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe tools/build.py
```

The default build creates the small release package. Pins are in `runtime-lock.json`.
See [release notes](CHANGELOG.md), [validation](docs/TEST_REPORT.md), and
[licenses](THIRD_PARTY_NOTICES.md).

## Support and contributions

[Report a bug or suggest a feature](https://github.com/beyondsighttech/drishya/issues).
Include your NVDA and Windows versions and steps to reproduce the issue. Remove
private information before sharing logs. Pull requests are welcome.

[All releases](https://github.com/beyondsighttech/drishya/releases)
include the installer and its SHA256 checksum.

# Drishya validation

## 0.2.1

The full suite passed 74 tests, including the pinned SmolVLM2 runtime test.
On an isolated NVDA 2026.3.1 desktop, the Tools command opened Settings.
The integration test verified the labels, values, and access keys for description
detail, maximum image size, and CPU threads, plus their Tab order. NVDA's Input
Gestures listed four assignable commands for screen, window, focus, and navigator
object descriptions. Speech playback was off during the isolated test.

## 0.2.0

Validated with NVDA 2026.3.1 on Windows x64 and Python 3.13.17.
Capture/menu work runs through wx.CallAfter after the script returns, so the
native menu loop does not hold NVDA's non-reentrant script pump. Settings
receives focus after it is shown.

Focused regressions cover deferred menu execution and saved target coordinates,
settings availability after capture failure, missing-model prompts without an
automatic download, remembering Later, and no prompt for installed models.

WGC is an optional, feature-detected adapter over NVDA's internal capture helper.
Checks cover BGRA-to-RGB conversion, unsupported backends, keeping Screen Curtain
enabled during successful capture, and refusing GDI fallback after WGC fails with
the curtain enabled. Real Screen Curtain capture still needs confirmation on the
an interactive desktop; isolated/headless capture is not proof of that.

Release downloads contain three assets only: the SmolVLM2 language model, its
full-precision projector and llama.cpp CPU runtime (661,376,837 download bytes).
No Mirage weights, Cactus runtime or embedded Python are in the release download.
The model choice uses prior photo-description comparisons; it is not a claim of
universal accuracy or lossless quantization.

Existing regression coverage remains for geometry, prompt bounds, model process
ownership, parent-exit cleanup, authentication, cancellation and atomic setup.
End-user instructions are in README.md and the bundled HTML guide.

Final checks for 0.2.0 passed with 70 unit/regression tests, one separately run real SmolVLM2 test, valid archive CRCs and no bundled model binaries. The corrected NVDA 2026.3.1 private-desktop integration report passed with the installed add-on, settings and result flow. Physical menu speech and real Screen Curtain capture require confirmation on the user desktop.

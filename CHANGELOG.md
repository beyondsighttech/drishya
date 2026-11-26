# Release notes

## 0.2.1

- Open Drishya settings from NVDA’s Tools menu.
- Correct the labels and access keys NVDA reports for description detail, maximum image size, and CPU threads.
- Add assignable gestures to describe the entire screen, current window, current focus, and navigator object directly.

## 0.2.0

- Run capture/menu work outside NVDA's script pump, keeping speech and input responsive.
- Keep menu/Settings available when capture fails; focus controls after showing dialogs.
- Offer Download or Later after installation/restart when the model is missing.
- Distribute a small add-on; download only SmolVLM2 and its CPU runtime separately.
- Use available Windows Graphics Capture without disabling Screen Curtain;
  otherwise explain the capture limitation instead of describing black pixels.
- Preserve checksum verification, cancellation and local process safeguards.

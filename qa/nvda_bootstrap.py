"""Loaded only in the isolated NVDA QA configuration, never in the release."""
import json
import sys
import traceback
from pathlib import Path

import api
import globalPluginHandler
import globalPlugins
import globalVars
import gui
import versionInfo
import wx


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        self.profile = Path(globalVars.appArgs.configPath)
        self.root = Path((self.profile / "workspace.txt").read_text(encoding="utf-8"))
        self.report = {"version": versionInfo.version, "checks": []}
        self.model_profile = (self.profile / "model-profile.txt").read_text(encoding="ascii").strip()
        self.report["model_profile"] = self.model_profile
        self.plugin = None
        self.timer = wx.CallLater(2500, self.run)

    def check(self, name, passed):
        self.report["checks"].append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    def run(self):
        try:
            from systemUtils import _getDesktopName
            self.report["desktop"] = _getDesktopName()
            self.check("QA runs on the explicitly private desktop", self.report["desktop"] == "DrishyaQA")
            import speech
            speech.setSpeechMode(speech.SpeechMode.off)
            from globalPlugins.drishya import GlobalPlugin as Drishya
            from globalPlugins.drishya.capture import Snapshot
            from globalPlugins.drishya.engine import Engine
            from globalPlugins.drishya.geometry import Rect
            from globalPlugins.drishya.settings import Options
            self.plugin = next((p for p in globalPluginHandler.runningPlugins if isinstance(p, Drishya)), None) or Drishya()
            self.check("public API import and plugin initialization", self.plugin.toolsItem is not None)
            self.check("NVDA script gesture", "kb:NVDA+shift+i" in self.plugin.script_drishyaMenu.gestures)
            self.plugin._show_settings()
            self.check("native settings and config defaults", self.plugin.settingsDialog.read_options() == self.plugin.options())
            self.plugin._save_options(Options(detail="concise", speak=False))
            self.plugin._close_settings()
            self.plugin.runtime = self.root / "build/runtime"
            self.plugin.engine = Engine(self.plugin.runtime)
            captured = []
            original_menu = self.plugin._open_menu
            self.plugin._open_menu = lambda snapshot, focus, nav, error=None: captured.append(snapshot)
            import ui
            capture_messages = []
            original_message = ui.message
            try:
                ui.message = capture_messages.append
                self.plugin._capture_and_open(None, None)
            finally:
                ui.message = original_message
            self.plugin._open_menu = original_menu
            self.report["display_capture"] = {"available": bool(captured and captured[0]), "messages": capture_messages}
            image = wx.Image(str(self.root / "qa/artifacts/photo-library.png"), wx.BITMAP_TYPE_PNG)
            rect = Rect(0, 0, image.GetWidth(), image.GetHeight())
            fixture = Snapshot(image, rect)
            if not captured or captured[0] is None:
                captured = [fixture]
            original_popup = gui.mainFrame.PopupMenu
            menu_labels = []
            try:
                gui.mainFrame.PopupMenu = lambda menu: menu_labels.extend(item.GetItemLabelText() for item in menu.GetMenuItems())
                self.plugin._open_menu(captured[0], captured[0].desktop, captured[0].desktop)
            finally:
                gui.mainFrame.PopupMenu = original_popup
            self.check("native context menu contains all three capture modes", all(
                label in menu_labels for label in ("Entire screen", "Current focus", "Navigator object")))
            self.plugin._describe_target(fixture, rect, "Integration QA")
            self.attempts = 0
            self.timer = wx.CallLater(100, self.poll)
        except Exception:
            self.finish(traceback.format_exc())

    def poll(self):
        try:
            self.attempts += 1
            if self.plugin.lastResult is None:
                if self.attempts > 400:
                    raise RuntimeError("NVDA description timed out: " + self.plugin.resultDialog.description.GetValue())
                self.timer = wx.CallLater(100, self.poll)
                return
            text = self.plugin.lastResult.text
            self.check("real model completion in NVDA dialog", self.plugin.resultDialog.description.GetValue() == text)
            self.check("result Copy is enabled", self.plugin.resultDialog.copyButton.IsEnabled())
            copied = []
            original_copy = api.copyToClip
            try:
                api.copyToClip = lambda value: copied.append(value) or True
                self.plugin._copy(text)
            finally:
                api.copyToClip = original_copy
            self.check("Copy action receives full description", copied == [text])
            self.report["clipboard_note"] = "Clipboard sink substituted to preserve the user's current clipboard."
            self.plugin._close_result()
            self.check("closing discards captured image", self.plugin.image is None)
            self.plugin._show_last()
            self.check("last result is reviewable", self.plugin.resultDialog.description.GetValue() == text)
            self.plugin._close_result()
            self.plugin._session_changed(isNowLocked=True)
            self.timer = wx.CallLater(100, self.finish_lock)
        except Exception:
            self.finish(traceback.format_exc())

    def finish_lock(self):
        try:
            self.check("lock event discards cached result", self.plugin.lastResult is None)
            self.plugin.terminate()
            self.check("plugin termination removes job callbacks", not self.plugin.controller.alive)
            self.plugin.terminate()
            self.finish()
        except Exception:
            self.finish(traceback.format_exc())

    def finish(self, error=None):
        if error:
            self.report["error"] = error
        self.report["passed"] = error is None and all(c["passed"] for c in self.report["checks"])
        if self.plugin:
            try:
                self.plugin.terminate()
            except Exception:
                self.report["cleanup_error"] = traceback.format_exc()
        (self.profile / "result.json").write_text(json.dumps(self.report, indent=2), encoding="utf-8")
        wx.CallAfter(wx.GetApp().ExitMainLoop)

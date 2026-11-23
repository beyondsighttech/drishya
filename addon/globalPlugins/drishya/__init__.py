"""Drishya: private, local image descriptions for NVDA."""
import dataclasses
import json
import threading
from pathlib import Path

import addonHandler
import api
import config
import globalPluginHandler
import globalVars
import gui
import ui
import wx
from scriptHandler import script
from gui.message import MessageDialog, ReturnCode
from utils.security import isRunningOnSecureDesktop, post_sessionLockStateChanged
from winAPI.sessionTracking import isLockScreenModeActive

from .assets import install_runtime, runtime_location
from .capture import capture_snapshot
from .controller import JobController
from .dialogs import ResultDialog, SettingsDialog
from .engine import Engine
from .geometry import Rect
from .settings import ADDON_VERSION, MODEL_NAME, CONFIG_SPEC, Options

addonHandler.initTranslation()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = "Drishya"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._terminated = False
        self.controller = JobController(wx.CallAfter)
        self.setupController = JobController(wx.CallAfter)
        self.resultDialog = None
        self.settingsDialog = None
        self.downloadDialog = None
        self._menuOpen = False
        self._menuPending = False
        self._promptTimer = None
        self.lastResult = None
        self.image = None
        self.toolsItem = None
        self._session_registered = False
        self._idleTimer = None
        self.package = Path(__file__).resolve().parent
        self.data = Path(globalVars.appArgs.configPath) / "drishya"
        self.runtime = runtime_location(self.package, self.data)
        self.engine = Engine(self.runtime)
        if globalVars.appArgs.secure:
            return
        config.conf.spec["drishya"] = CONFIG_SPEC
        post_sessionLockStateChanged.register(self._session_changed)
        self._session_registered = True
        self._idleTimer = wx.Timer(gui.mainFrame)
        gui.mainFrame.Bind(wx.EVT_TIMER, self._release_idle, self._idleTimer)
        self.toolsItem = gui.mainFrame.sysTrayIcon.toolsMenu.Append(wx.ID_ANY, "Drishya &settings…")
        gui.mainFrame.Bind(wx.EVT_MENU, lambda event: wx.CallAfter(self._show_settings), self.toolsItem)
        self._promptTimer = wx.CallLater(2000, self._offer_download)

    def options(self):
        defaults = dataclasses.asdict(Options())
        values = config.conf["drishya"]
        return Options(**{name: values.get(name, default) for name, default in defaults.items()})

    def _allowed(self):
        if self._terminated:
            return False
        if globalVars.appArgs.secure or isRunningOnSecureDesktop() or isLockScreenModeActive():
            ui.message("Drishya is unavailable while the desktop is locked or secure.")
            return False
        return True

    @staticmethod
    def _location(obj):
        try:
            return Rect(*(int(value) for value in obj.location))
        except (AttributeError, TypeError, ValueError):
            return None

    @script(description="Open the Drishya local image description menu", gesture="kb:NVDA+shift+i")
    def script_drishyaMenu(self, gesture):
        if not self._allowed():
            return
        if self._menuOpen or self._menuPending:
            return
        if self.downloadDialog:
            self.downloadDialog.Raise()
            return
        if self.controller.busy or self.controller.running or self.setupController.busy or self.setupController.running:
            ui.message("Drishya is busy. Close the current dialog to cancel first.")
            return
        focus = self._location(api.getFocusObject())
        nav = self._location(api.getNavigatorObject())
        self._menuPending = True
        wx.CallAfter(self._capture_and_open, focus, nav)

    def _capture_and_open(self, focus, nav):
        if not self._allowed() or self._menuOpen or self.downloadDialog:
            self._menuPending = False
            return
        capture_error = None
        try:
            snapshot = capture_snapshot()
        except Exception as error:
            snapshot, capture_error = None, str(error)
        self._menuPending = False
        # PopupMenu has its own native message loop. Never enter it from NVDA's
        # non-reentrant core/script pump, or speech/events/watchdog stop pumping.
        self._open_menu(snapshot, focus, nav, capture_error)

    def _open_menu(self, snapshot, focus, nav, capture_error=None):
        if not self._allowed() or self._menuOpen:
            return
        menu = wx.Menu()
        handlers = []

        def describe(target, title):
            if snapshot is None:
                ui.message(capture_error or "Screen capture is unavailable. Please try again.")
                return
            self._describe_target(snapshot, target, title)

        def item(label, callback, enabled=True):
            entry = menu.Append(wx.ID_ANY, label)
            entry.Enable(enabled)
            gui.mainFrame.Bind(wx.EVT_MENU, lambda event: wx.CallAfter(callback), id=entry.GetId())
            handlers.append(entry.GetId())

        item("&Entire screen", lambda: describe(snapshot.desktop if snapshot else None, "Entire screen"))
        item("Current &focus", lambda: describe(focus, "Current focus"), focus is not None)
        item("&Navigator object", lambda: describe(nav, "Navigator object"), nav is not None)
        menu.AppendSeparator()
        item("&Last description", self._show_last, self.lastResult is not None)
        item("&Settings…", self._show_settings)
        gui.mainFrame.prePopup()
        self._menuOpen = True
        try:
            ui.message("Drishya image description menu")
            gui.mainFrame.PopupMenu(menu)
        finally:
            self._menuOpen = False
            gui.mainFrame.postPopup()
            for identifier in handlers:
                gui.mainFrame.Unbind(wx.EVT_MENU, id=identifier)
            menu.Destroy()

    def _describe_target(self, snapshot, target, title):
        if not self._allowed():
            return
        if not self._runtime_installed():
            self._offer_download(force=True)
            return
        try:
            if target is None:
                raise ValueError("This object has no visible image area. Bring it into view and try again.")
            image = snapshot.crop(target, self.options().max_side)
        except Exception as error:
            ui.message(str(error))
            return
        self._close_result()
        self.image = image
        self.resultDialog = ResultDialog(gui.mainFrame, title, self._retry, self._close_result, self._copy)
        self._show_dialog(self.resultDialog)
        self._retry()

    def _show_dialog(self, dialog):
        gui.mainFrame.prePopup()
        try:
            dialog.Show()
            dialog.Raise()
            if hasattr(dialog, "SetFocus"):
                dialog.SetFocus()
            if hasattr(dialog, "focus_initial"):
                wx.CallAfter(dialog.focus_initial)
        finally:
            gui.mainFrame.postPopup()

    def _retry(self):
        if not self._allowed() or not self.image or not self.resultDialog or self.controller.busy:
            return
        if self.controller.running or self.setupController.running:
            ui.message("The previous task is still cancelling. Please try again in a moment.")
            return
        if self._idleTimer:
            self._idleTimer.Stop()
        options, image, engine = self.options(), self.image, self.engine
        self.resultDialog.set_pending()
        self.controller.start(
            lambda cancel: engine.describe(image, options.detail, options.threads, cancel),
            self._result, self._error)

    def _result(self, result):
        if not self._allowed() or not self.resultDialog:
            return
        self.lastResult = result
        self.resultDialog.show_result(result.text, result.model, result.seconds)
        if self._idleTimer:
            self._idleTimer.StartOnce(300_000)
        ui.message(result.text if self.options().speak else "Drishya description ready.")

    def _error(self, error):
        if self._allowed() and self.resultDialog:
            self.resultDialog.show_error(error)
            ui.message(str(error))

    def _copy(self, text):
        if self._allowed() and text:
            ui.message("Description copied." if api.copyToClip(text) else "Clipboard is busy. Please try Copy again.")

    def _close_result(self):
        if self.controller.cancel() and not self._terminated:
            self._recycle_engine()
        self.image = None
        dialog, self.resultDialog = self.resultDialog, None
        if dialog:
            dialog.Destroy()

    def _show_last(self):
        if not self._allowed() or not self.lastResult:
            return
        self._close_result()
        self.resultDialog = ResultDialog(gui.mainFrame, "Last description", self._retry, self._close_result, self._copy)
        self.resultDialog.can_retry = False
        result = self.lastResult
        self.resultDialog.show_result(result.text, result.model, result.seconds)
        self._show_dialog(self.resultDialog)

    def _show_settings(self, event=None):
        if not self._allowed():
            return
        if self.controller.busy or self.controller.running:
            ui.message("Cancel the current description before opening Settings.")
            return
        if self.settingsDialog:
            self.settingsDialog.Raise()
            wx.CallAfter(self.settingsDialog.focus_initial)
            return
        self.settingsDialog = SettingsDialog(gui.mainFrame, self.options(), self._save_options,
                                              self._setup, self._runtime_installed)
        self.settingsDialog.on_close = self._close_settings
        self._show_dialog(self.settingsDialog)

    def _runtime_installed(self):
        if not (self.runtime / "inventory.json").is_file():
            return False
        for name, size in (("SmolVLM2-500M-Video-Instruct-Q8_0.gguf", 436808704),
                           ("mmproj-SmolVLM2-500M-Video-Instruct-f16.gguf", 199470624)):
            path = self.runtime / "models" / name
            if not path.is_file() or path.stat().st_size != size:
                return False
        return any((self.runtime / "llama").rglob("llama-server.exe"))

    def _offer_download(self, force=False):
        if not self._allowed() or self._runtime_installed() or self.downloadDialog:
            return
        if not force and (self._menuOpen or self._menuPending or self.settingsDialog or self.resultDialog or
                          config.conf["drishya"].get("setup_prompt_version", "") == ADDON_VERSION):
            return
        config.conf["drishya"]["setup_prompt_version"] = ADDON_VERSION
        dialog = MessageDialog(gui.mainFrame,
            "Welcome to Drishya. Download the " + MODEL_NAME + " image description model to get started. "
            "The one-time download is about 662 MB and needs internet. "
            "Descriptions work offline afterward. Download now?",
            title="Drishya — download image description model", buttons=())
        dialog.addButton(ReturnCode.YES, "&Download", callback=lambda payload: self._download_answer(True))
        dialog.addButton(ReturnCode.NO, "&Later", defaultFocus=True, fallbackAction=True,
                         callback=lambda payload: self._download_answer(False))
        self.downloadDialog = dialog
        self._show_dialog(dialog)

    def _download_answer(self, accepted):
        self.downloadDialog = None
        if accepted:
            wx.CallAfter(self._begin_download)

    def _begin_download(self):
        if not self._allowed():
            return
        self._show_settings()
        if self.settingsDialog:
            self._setup(self.settingsDialog)

    def _close_settings(self):
        if self.setupController.cancel() and not self._terminated:
            self._recycle_engine()
        dialog, self.settingsDialog = self.settingsDialog, None
        if dialog:
            dialog.Destroy()

    def _save_options(self, options):
        for name, value in dataclasses.asdict(options).items():
            config.conf["drishya"][name] = value
        self.lastResult = None
        self._recycle_engine()
        ui.message("Drishya settings saved.")

    def _recycle_engine(self):
        previous, self.engine = self.engine, Engine(self.runtime)
        threading.Thread(target=previous.close, daemon=True, name="Drishya cleanup").start()

    def _release_idle(self, event):
        if not self.controller.busy and not self.setupController.busy:
            self._recycle_engine()

    def _setup(self, dialog):
        if not self._allowed():
            return
        if self.setupController.busy:
            self.setupController.cancel()
            self._recycle_engine()
            dialog.set_setup_state(False, "Setup cancelled. You can retry.")
            return
        if self.setupController.running:
            ui.message("Setup is still cancelling. Please try again in a moment.")
            return
        lock = json.loads((self.package / "runtime-lock.json").read_text(encoding="utf-8"))
        dialog.set_setup_state(True, "Downloading and verifying the image description model…")
        dialog.setupButton.SetFocus()
        ui.message("Downloading the SmolVLM2 model. Press Escape to cancel.")
        engine = self.engine
        expected_generation = self.setupController.generation + 1
        totals = {a["name"]: a["size"] for a in lock["assets"]}
        downloaded = dict.fromkeys(totals, 0)
        last_percent = [-1]

        def progress(name, current, total):
            downloaded[name] = current
            percent = int(100 * sum(downloaded.values()) / sum(totals.values()))
            if percent != last_percent[0]:
                last_percent[0] = percent
                wx.CallAfter(update, percent)

        def update(percent):
            if (not self._terminated and self.settingsDialog is dialog
                    and self.setupController.generation == expected_generation):
                dialog.progress.SetValue(percent)

        def work(cancel):
            engine.close()
            cache = self.data / "downloads"
            install_runtime(lock, self.runtime, cache, cancel, progress, cleanup_cache=True)
            return True

        def done(value):
            self.engine = Engine(self.runtime)
            if self.settingsDialog is dialog:
                dialog.set_setup_state(False, "Setup complete. Ready offline.")
                ui.message("Drishya model is ready. You can describe images offline.")

        def failed(error):
            self.engine = Engine(self.runtime)
            if self.settingsDialog is dialog:
                dialog.set_setup_state(False, "Setup failed: " + str(error))
                ui.message("Drishya setup failed. " + str(error))

        self.setupController.start(work, done, failed)

    def _session_changed(self, isNowLocked):
        if isNowLocked:
            wx.CallAfter(self._discard_locked)

    def _discard_locked(self):
        if self._terminated:
            return
        self._close_result()
        self._close_settings()
        if self.downloadDialog:
            self.downloadDialog.Destroy()
            self.downloadDialog = None
        self.lastResult = None
        self._recycle_engine()

    def terminate(self):
        if self._terminated:
            return
        self._terminated = True
        self.controller.close()
        self.setupController.close()
        self._close_result()
        self._close_settings()
        if self._promptTimer:
            self._promptTimer.Stop()
        if self.downloadDialog:
            self.downloadDialog.Destroy()
            self.downloadDialog = None
        if self._session_registered:
            post_sessionLockStateChanged.unregister(self._session_changed)
        if self.toolsItem:
            gui.mainFrame.Unbind(wx.EVT_MENU, id=self.toolsItem.GetId())
            gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self.toolsItem)
            self.toolsItem.Destroy()
        if self._idleTimer:
            self._idleTimer.Stop()
            gui.mainFrame.Unbind(wx.EVT_TIMER, source=self._idleTimer)
        threading.Thread(target=self.engine.close, daemon=True, name="Drishya shutdown").start()
        super().terminate()

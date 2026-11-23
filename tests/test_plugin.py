"""NVDA API adapter checks using real wx, with explicit NVDA API test doubles."""
import importlib.util
import importlib.machinery
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import wx
import tests


class Action:
    def __init__(self):
        self.handlers = []
    def register(self, handler):
        self.handlers.append(handler)
    def unregister(self, handler):
        self.handlers.remove(handler)


class Configuration(dict):
    def __init__(self):
        super().__init__(drishya={})
        self.spec = {}


class Prompt:
    def __init__(self, parent, message, title, buttons=()):
        self.message, self.title = message, title
        self.buttons = {}
    def addButton(self, code, label, **kwargs):
        self.buttons[code] = (label, kwargs)
        return self
    def Show(self):
        pass
    def Raise(self):
        pass
    def Destroy(self):
        pass


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.frame = wx.Frame(None, title="NVDA API test")
        self.frame.prePopup = lambda: None
        self.frame.postPopup = lambda: None
        self.frame.sysTrayIcon = types.SimpleNamespace(toolsMenu=wx.Menu())
        self.api = types.ModuleType("api")
        self.api.getFocusObject = lambda: types.SimpleNamespace(location=(100, 200, 300, 400))
        self.api.getNavigatorObject = lambda: types.SimpleNamespace(location=(20, 40, 60, 80))
        self.api.copyToClip = lambda text: True
        self.messages = []
        self.action = Action()
        self.locked = False
        self.arguments = types.SimpleNamespace(secure=False, configPath=self.temp.name)
        modules = {
            "api": self.api,
            "addonHandler": types.SimpleNamespace(initTranslation=lambda: None),
            "config": types.SimpleNamespace(conf=Configuration()),
            "globalVars": types.SimpleNamespace(appArgs=self.arguments),
            "globalPluginHandler": types.SimpleNamespace(GlobalPlugin=type("Base", (), {"terminate": lambda self: None})),
            "gui": types.SimpleNamespace(mainFrame=self.frame),
            "gui.message": types.SimpleNamespace(MessageDialog=Prompt, ReturnCode=types.SimpleNamespace(YES=wx.ID_YES, NO=wx.ID_NO)),
            "scriptHandler": types.SimpleNamespace(script=lambda **kwargs: lambda fn: fn),
            "ui": types.SimpleNamespace(message=self.messages.append),
            "utils.security": types.SimpleNamespace(post_sessionLockStateChanged=self.action,
                                                      isRunningOnSecureDesktop=lambda: False),
            "winAPI.sessionTracking": types.SimpleNamespace(isLockScreenModeActive=lambda: self.locked),
        }
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        path = tests.ROOT / "addon/globalPlugins/drishya/__init__.py"
        loader = importlib.machinery.SourceFileLoader("drishya.test_entry", str(path))
        spec = importlib.util.spec_from_loader("drishya.test_entry", loader, is_package=False)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module
        self.plugin = module.GlobalPlugin()
        self.addCleanup(self.frame.Destroy)
        self.addCleanup(self.plugin.terminate)

    def test_targets_are_saved_before_popup_changes_focus(self):
        captured = object()
        self.module.capture_snapshot = lambda: captured
        observed = []
        self.plugin._open_menu = lambda snapshot, focus, nav, error=None: observed.append((snapshot, focus, nav))
        pending = []
        with patch.object(wx, "CallAfter", side_effect=lambda function, *args: pending.append((function, args))):
            self.plugin.script_drishyaMenu(None)
        self.assertEqual(observed, [], "PopupMenu must not run inside NVDA's script pump")
        self.api.getFocusObject = lambda: types.SimpleNamespace(location=(999, 999, 20, 20))
        pending[0][0](*pending[0][1])
        self.assertIs(observed[0][0], captured)
        self.assertEqual(observed[0][1].x, 100)
        self.assertEqual(observed[0][2].x, 20)

    def test_capture_error_does_not_hide_settings_menu(self):
        def fail():
            raise ValueError("Screen Curtain is enabled")
        self.module.capture_snapshot = fail
        observed, pending = [], []
        self.plugin._open_menu = lambda *args: observed.append(args)
        with patch.object(wx, "CallAfter", side_effect=lambda function, *args: pending.append((function, args))):
            self.plugin.script_drishyaMenu(None)
        pending[0][0](*pending[0][1])
        self.assertIsNone(observed[0][0])
        self.assertIn("Screen Curtain", observed[0][3])

    def test_missing_model_prompts_without_starting_download(self):
        self.plugin._runtime_installed = lambda: False
        self.plugin._offer_download()
        self.assertIsNotNone(self.plugin.downloadDialog)
        self.assertIn("SmolVLM2", self.plugin.downloadDialog.message)
        self.assertFalse(self.plugin.setupController.busy)

    def test_installed_model_does_not_prompt(self):
        self.plugin._runtime_installed = lambda: True
        self.plugin._offer_download()
        self.assertIsNone(self.plugin.downloadDialog)

    def test_later_is_remembered_but_description_can_request_setup(self):
        self.plugin._runtime_installed = lambda: False
        self.plugin._offer_download()
        self.plugin._download_answer(False)
        self.plugin._offer_download()
        self.assertIsNone(self.plugin.downloadDialog)
        self.plugin._offer_download(force=True)
        self.assertIsNotNone(self.plugin.downloadDialog)

    def test_lock_blocks_capture(self):
        self.locked = True
        self.module.capture_snapshot = lambda: self.fail("Captured locked desktop")
        self.plugin.script_drishyaMenu(None)
        self.assertIn("locked", self.messages[-1].lower())

    def test_termination_unregisters_and_cancels(self):
        self.assertEqual(len(self.action.handlers), 1)
        self.plugin.terminate()
        self.assertEqual(self.action.handlers, [])
        self.assertFalse(self.plugin.controller.alive)

    def test_lock_discards_cached_description(self):
        self.plugin.lastResult = object()
        with patch.object(wx, "CallAfter", side_effect=lambda callback: callback()):
            self.plugin._session_changed(isNowLocked=True)
        self.assertIsNone(self.plugin.lastResult)

    def test_cancelled_setup_replaces_closed_engine(self):
        previous = self.plugin.engine
        previous.close()
        self.plugin.setupController.busy = True
        self.plugin._close_settings()
        self.assertIsNot(self.plugin.engine, previous)
        self.assertFalse(self.plugin.engine._shutdown.is_set())

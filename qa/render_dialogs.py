"""Render this add-on's own native wx windows for visual QA."""
import ctypes
from ctypes import wintypes
import sys
from pathlib import Path
import wx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tests
from drishya.dialogs import ResultDialog, SettingsDialog
from drishya.settings import Options


def save_window(window, name):
    width, height = window.GetSize()
    bitmap = wx.Bitmap(width, height, 24)
    dc = wx.MemoryDC(bitmap)
    print_window = ctypes.windll.user32.PrintWindow
    print_window.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    print_window.restype = wintypes.BOOL
    try:
        if not print_window(window.GetHandle(), dc.GetHandle(), 0):
            raise RuntimeError("Native window rendering failed")
    finally:
        dc.SelectObject(wx.NullBitmap)
    path = ROOT / "qa/artifacts" / name
    bitmap.ConvertToImage().SaveFile(str(path), wx.BITMAP_TYPE_PNG)
    print(path, flush=True)


app = wx.App(False)
result = ResultDialog(None, "Navigator object", lambda: None, lambda: None, lambda text: None)
result.show_result("A photo-library interface with a dark blue header and a white background. "
                   "A mountain illustration is on the left and a blue Upload button is at the bottom right. "
                   "Visible text includes Photo Library, Summer holiday, and 12 photos selected.",
                   "SmolVLM2 500M Q8", 4.2)
result.Show()

def first():
    save_window(result, "result-dialog.png")
    result.Destroy()
    settings = SettingsDialog(None, Options(), lambda value: None, lambda: None, lambda: True)
    settings.Show()
    def second():
        save_window(settings, "settings-dialog.png")
        settings.Destroy()
        app.ExitMainLoop()
    wx.CallLater(350, second)

wx.CallLater(350, first)
app.MainLoop()

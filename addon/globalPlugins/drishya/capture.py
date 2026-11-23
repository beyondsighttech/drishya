"""In-memory wx snapshots taken before the description menu is displayed."""
import ctypes
import io
from dataclasses import dataclass

import wx

from .engine import ImageData
from .geometry import Rect, fitted_size
from .wgc import capture_with_wgc

CURTAIN_MESSAGE = (
    "Screen Curtain is enabled. Please disable Screen Curtain before describing an image, then try again."
)


@dataclass
class Snapshot:
    image: wx.Image
    desktop: Rect
    backend: str = "GDI"

    def crop(self, target, max_side):
        region = target.clip(self.desktop)
        image = self.image.GetSubImage(wx.Rect(region.x - self.desktop.x,
                                               region.y - self.desktop.y,
                                               region.width, region.height))
        width, height = fitted_size(region.width, region.height, max_side)
        if (width, height) != (region.width, region.height):
            image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
        output = io.BytesIO()
        if not image.SaveFile(output, wx.BITMAP_TYPE_PNG):
            raise ValueError("Could not encode the screen image. Please try again.")
        return ImageData(output.getvalue(), bytes(image.GetData()), width, height)


def desktop_rect():
    metrics = ctypes.windll.user32.GetSystemMetrics
    desktop = Rect(*(int(metrics(i)) for i in (76, 77, 78, 79)))
    if desktop.width * desktop.height > 40_000_000:
        raise ValueError("The desktop is too large to capture. Reduce the monitor resolution and try again.")
    return desktop


def capture_snapshot():
    try:
        from screenCurtain import screenCurtain
    except ImportError:
        screenCurtain = None  # Standalone development tools, outside NVDA.
    curtain = screenCurtain is not None and screenCurtain.enabled
    desktop = desktop_rect()
    try:
        captured = capture_with_wgc(desktop)
        if captured is not None:
            return Snapshot(captured, desktop, "Windows Graphics Capture")
    except RuntimeError:
        if curtain:
            raise ValueError("Windows Graphics Capture is unavailable. " + CURTAIN_MESSAGE) from None
    if curtain:
        raise ValueError(CURTAIN_MESSAGE)
    bitmap = wx.Bitmap(desktop.width, desktop.height, 24)
    memory = wx.MemoryDC(bitmap)
    try:
        screen = wx.ScreenDC()
        if not memory.Blit(0, 0, desktop.width, desktop.height, screen, desktop.x, desktop.y):
            raise ValueError("Screen capture failed. Please try again.")
    finally:
        memory.SelectObject(wx.NullBitmap)
    image = bitmap.ConvertToImage()
    if not image.IsOk():
        raise ValueError("Screen capture returned no image.")
    return Snapshot(image, desktop)

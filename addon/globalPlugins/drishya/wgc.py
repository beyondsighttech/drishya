"""Optional NVDA WGC adapter, isolated from the add-on's compatibility contract.

NVDA currently exposes this capture backend through an internal helper. Probe it
at capture time; builds without it retain GDI or the Screen Curtain warning.
"""
import wx


def capture_with_wgc(rect):
    try:
        from contentRecog import RecogImageInfo, _wgcCapture
        supported = getattr(_wgcCapture, "isSupported", None)
        capture = getattr(_wgcCapture, "captureImage", None)
        if not callable(supported) or not callable(capture) or not supported():
            return None
    except (ImportError, AttributeError, OSError):
        return None
    try:
        info = RecogImageInfo(rect.x, rect.y, rect.width, rect.height, 1.0)
        raw = bytes(capture(info))
        if len(raw) != rect.width * rect.height * 4:
            raise RuntimeError("Windows capture returned invalid pixel dimensions.")
        rgb = bytearray(rect.width * rect.height * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = raw[2::4], raw[1::4], raw[0::4]
        image = wx.Image(rect.width, rect.height)
        image.SetData(bytes(rgb))
        return image
    except Exception as error:
        raise RuntimeError("Windows Graphics Capture failed.") from error

"""CPU end-to-end benchmark with labeled local fixtures; no cloud inference."""
import argparse
import ctypes
import io
import json
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tests
from drishya.engine import Engine, ImageData


def fixtures(destination):
    destination.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 28)
    small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 21)
    image = Image.new("RGB", (800, 520), "#f6f7fb")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 800, 65), fill="#18253e")
    draw.text((24, 14), "Photo Library", fill="white", font=font)
    draw.text((28, 98), "Summer holiday", fill="#142030", font=font)
    draw.text((28, 145), "12 photos selected", fill="#384961", font=small)
    draw.rounded_rectangle((28, 206, 450, 402), radius=12, fill="#dde9f5")
    draw.polygon([(40, 380), (188, 245), (250, 318), (335, 260), (440, 380)], fill="#487452")
    draw.ellipse((350, 224, 397, 271), fill="#e4b536")
    draw.rounded_rectangle((560, 416, 746, 482), radius=10, fill="#185be1")
    draw.text((595, 430), "Upload", fill="white", font=font)
    image.save(destination / "photo-library.png")
    shapes = Image.new("RGB", (640, 480), "#fff6e8")
    draw = ImageDraw.Draw(shapes)
    draw.ellipse((68, 100, 260, 292), fill="#d92e33")
    draw.rectangle((372, 116, 546, 290), fill="#185bdd")
    draw.text((70, 337), "Red circle", font=font, fill="black")
    draw.text((360, 337), "Blue square", font=font, fill="black")
    shapes.save(destination / "shapes.png")
    return [destination / "photo-library.png", destination / "shapes.png"]


def image_data(path, max_side=1024):
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_side, max_side))
        data = io.BytesIO()
        image.save(data, format="PNG")
        return ImageData(data.getvalue(), image.tobytes(), image.width, image.height)


def memory_usage(pid):
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("peak", "working", "peak_paged", "paged",
                                                "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x0410, False, pid)
    if not handle:
        return None
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        read = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        read.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        read.restype = wintypes.BOOL
        if not read(handle, ctypes.byref(counters), counters.cb):
            return None
        return {"working_set_mb": round(counters.working / 1_000_000, 1),
                "peak_working_set_mb": round(counters.peak / 1_000_000, 1)}
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", default="build/runtime")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--detail", choices=["concise", "detailed"], default="detailed")
    args = parser.parse_args()
    output = ROOT / "qa/artifacts"
    paths = fixtures(output) + [Path(p) for p in args.image]
    records = []
    engine = Engine(ROOT / args.runtime)
    try:
        for profile in ["smol"]:
            for path in paths:
                started = time.monotonic()
                try:
                    result = engine.describe(image_data(path), args.detail, 4, threading.Event())
                    record = {"profile": profile, "fixture": path.name, "seconds": round(result.seconds, 3),
                              "text": result.text, "model_process_memory": memory_usage(engine.process.pid)}
                except Exception as error:
                    record = {"profile": profile, "fixture": path.name, "seconds": round(time.monotonic() - started, 3), "error": repr(error)}
                records.append(record)
                print(json.dumps(record, ensure_ascii=True), flush=True)
                (output / ("benchmark-smol-" + args.detail + ".json")).write_text(json.dumps(records, indent=2), encoding="utf-8")
    finally:
        engine.close()


if __name__ == "__main__":
    main()

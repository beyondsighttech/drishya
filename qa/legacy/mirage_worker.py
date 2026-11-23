"""Isolated Cactus C ABI adapter. No package downloads or telemetry."""
import base64
import ctypes
import json
import sys
from pathlib import Path


def main():
    runtime, threads = Path(sys.argv[1]), int(sys.argv[2])
    lib = ctypes.CDLL(str(runtime / "cactus/libcactus.dll"))
    lib.cactus_load.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
    lib.cactus_load.restype = ctypes.c_int
    lib.cactus_last_error.restype = ctypes.c_char_p
    lib.cactus_set_threads.argtypes = [ctypes.c_int]
    lib.cactus_set_threads.restype = None
    lib.cactus_describe.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                                   ctypes.c_char_p, ctypes.c_int]
    lib.cactus_describe.restype = ctypes.c_int
    weights = (runtime / "models/mirage.cact").read_bytes()
    if lib.cactus_load(weights, len(weights)) < 0:
        raise RuntimeError(lib.cactus_last_error().decode("utf-8", "replace"))
    del weights
    lib.cactus_set_threads(threads)
    buffer = ctypes.create_string_buffer(16 * 1024 * 1024)
    while line := sys.stdin.buffer.readline(16 * 1024 * 1024 + 1):
        try:
            if len(line) > 16 * 1024 * 1024:
                raise ValueError("Image request is too large.")
            request = json.loads(line)
            width, height = request["width"], request["height"]
            if not isinstance(width, int) or not isinstance(height, int) or not 0 < width <= 2048 or not 0 < height <= 2048:
                raise ValueError("Invalid image dimensions.")
            rgb = base64.b64decode(request["rgb"], validate=True)
            if len(rgb) != width * height * 3:
                raise ValueError("RGB image size mismatch.")
            options = json.dumps({"mask_format": "largest"}).encode()
            code = lib.cactus_describe(rgb, width, height, options, b"en", None, buffer, len(buffer))
            if code < 0:
                raise RuntimeError(lib.cactus_last_error().decode("utf-8", "replace"))
            response = json.loads(buffer.value)
        except Exception as error:
            response = {"error": str(error)}
        sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error": str(error)}), flush=True)

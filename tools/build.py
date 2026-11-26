"""Deterministic slim and complete offline NVDA add-on archives."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Build-time import must not execute the NVDA entry point.
sys.path.insert(0, str(ROOT / "addon/globalPlugins/drishya"))
from assets import BUDGET, verify_runtime

VERSION = "0.2.1"


def build_package(destination, full=False, runtime=None, addon_root=None):
    addon_root = Path(addon_root or ROOT / "addon")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    files = [(p, p.relative_to(addon_root).as_posix()) for p in sorted(addon_root.rglob("*"))
             if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts and "runtime" not in p.relative_to(addon_root).parts]
    if full:
        runtime = Path(runtime)
        verify_runtime(runtime)
        files += [(p, "globalPlugins/drishya/runtime/" + p.relative_to(runtime).as_posix())
                  for p in sorted(runtime.rglob("*")) if p.is_file()]
    installed_size = sum(p.stat().st_size for p, _ in files)
    if installed_size >= BUDGET:
        raise ValueError("Complete add-on exceeds the 1 GB installed disk budget.")
    name = f"drishya-{VERSION}" + ("-offline" if full else "") + ".nvda-addon"
    target = destination / name
    temporary = target.with_suffix(".partial")
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            for source, name in files:
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 23, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED if full else zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
                    while data := reader.read(1024 * 1024):
                        writer.write(data)
        with zipfile.ZipFile(temporary) as archive:
            if "manifest.ini" not in archive.namelist() or archive.testzip() is not None:
                raise ValueError("The NVDA add-on archive is invalid.")
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--runtime", default=str(ROOT / "build/runtime"))
    parser.add_argument("--output", default=str(ROOT / "dist"))
    parser.add_argument("--install-runtime", action="store_true", help="Download/verify the pinned runtime before building")
    args = parser.parse_args()
    if args.install_runtime:
        import threading
        from assets import install_runtime
        lock = json.loads((ROOT / "runtime-lock.json").read_text(encoding="utf-8"))
        install_runtime(lock, Path(args.runtime), ROOT / "runtime-cache", threading.Event(),
                        lambda name, done, total: None)
    package = build_package(args.output, args.full, args.runtime)
    with package.open("rb") as source:
        sha = hashlib.file_digest(source, "sha256").hexdigest()
    package.with_suffix(package.suffix + ".sha256").write_text(sha + "  " + package.name + "\n", encoding="ascii")
    print(json.dumps({"package": str(package), "bytes": package.stat().st_size, "sha256": sha}))


if __name__ == "__main__":
    main()

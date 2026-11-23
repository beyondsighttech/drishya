"""Verified, transactional runtime installation. No inference network services."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

BUDGET = 1_000_000_000
_install_lock = threading.Lock()


@contextmanager
def installation_guard(runtime):
    """OS locks survive module reloads and release automatically after a crash."""
    lock_path = runtime.with_name(runtime.name + ".install-lock")
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("Local model setup is already running. Wait for it to finish or cancel before retrying.") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Cancelled(Exception):
    pass


def runtime_location(package, data):
    package, data = Path(package), Path(data)
    bundled = package / "runtime"
    if (bundled.exists() or (package / "runtime-previous").exists()
            or (package / "runtime.install-lock").exists()
            or any(package.glob("runtime-staging-*"))):
        return bundled
    return data / "runtime"


def check_cancel(cancel):
    if cancel.is_set():
        raise Cancelled("Cancelled.")


def safe_path(root, name):
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(p in ("..", ".") or ":" in p for p in path.parts):
        raise ValueError("Unsafe path in runtime inventory or archive.")
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Runtime path escapes its directory.")
    return target


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def valid_asset(path, asset):
    return (path.is_file() and path.stat().st_size == asset["size"]
            and digest(path) == asset["sha256"])


def download_asset(asset, cache, cancel, progress=lambda *args: None):
    check_cancel(cancel)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = safe_path(cache, asset["name"])
    if valid_asset(target, asset):
        progress(asset["name"], asset["size"], asset["size"])
        return target
    temp = target.with_name(target.name + ".partial")
    try:
        request = Request(asset["url"], headers={"User-Agent": "Drishya/0.1"})
        total = 0
        with urlopen(request, timeout=10) as source, temp.open("wb") as output:
            while True:
                check_cancel(cancel)
                data = source.read(1024 * 1024)
                if not data:
                    break
                total += len(data)
                if total > asset["size"]:
                    raise ValueError("Download is larger than its verified size.")
                output.write(data)
                progress(asset["name"], total, asset["size"])
        check_cancel(cancel)
        if not valid_asset(temp, asset):
            raise ValueError("Runtime download failed its checksum. Please retry setup.")
        os.replace(temp, target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def extract_archive(source, destination, cancel, only_library=False):
    destination = Path(destination)
    total = 0
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            check_cancel(cancel)
            target = safe_path(destination, member.filename)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlinks are not allowed in runtime archives.")
            total += member.file_size
            if total > BUDGET:
                raise ValueError("Expanded runtime exceeds the 1 GB disk budget.")
            if member.is_dir():
                continue
            if only_library and member.filename != "cactus/libcactus.dll":
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as reader, target.open("wb") as writer:
                while data := reader.read(1024 * 1024):
                    check_cancel(cancel)
                    writer.write(data)


def lock_fingerprint(lock):
    return hashlib.sha256(json.dumps(lock, sort_keys=True).encode("utf-8")).hexdigest()


def write_inventory(root, lock=None):
    files = [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size, "sha256": digest(p)}
             for p in sorted(root.rglob("*")) if p.is_file() and p.name != "inventory.json"]
    if sum(f["size"] for f in files) > BUDGET - 2_000_000:
        raise ValueError("Installed runtime exceeds the 1 GB disk budget.")
    inventory = {"schema": 1, "files": files}
    if lock is not None:
        inventory["lock_sha256"] = lock_fingerprint(lock)
    (root / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")


def remove_owned_directory(path, parent):
    if (path.resolve() == parent.resolve() or not path.resolve().is_relative_to(parent.resolve())
            or path.is_symlink() or path.is_junction()):
        raise ValueError("Unsafe setup recovery directory.")
    shutil.rmtree(path)


def recover_installation(runtime, cancel):
    backup = runtime.with_name(runtime.name + "-previous")
    if backup.exists():
        if backup.is_symlink() or backup.is_junction():
            raise ValueError("Invalid setup recovery backup.")
        if not runtime.exists():
            verify_runtime(backup, cancel)
            backup.rename(runtime)
        else:
            try:
                verify_runtime(runtime, cancel)
            except ValueError:
                verify_runtime(backup, cancel)
                remove_owned_directory(runtime, runtime.parent)
                backup.rename(runtime)
            else:
                # A published verified runtime supersedes its generated backup.
                if not (backup / "inventory.json").is_file():
                    raise ValueError("Unrecognized setup backup directory.")
                remove_owned_directory(backup, runtime.parent)
    pattern = re.compile(re.escape(runtime.name) + r"-staging-[a-z0-9_]{8}")
    for orphan in runtime.parent.iterdir():
        check_cancel(cancel)
        if pattern.fullmatch(orphan.name) and orphan.is_dir():
            remove_owned_directory(orphan, runtime.parent)


def cleanup_download_cache(cache, lock):
    """Remove only this pinned setup's generated files, under the install lock."""
    cache = Path(cache)
    for asset in lock["assets"]:
        path = safe_path(cache, asset["name"])
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".partial").unlink(missing_ok=True)
    try:
        cache.rmdir()
    except OSError:
        pass  # Unrelated files are preserved.


def verify_runtime(root, cancel=None):
    root = Path(root)
    cancel = cancel or threading.Event()
    try:
        inventory = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
        files = inventory["files"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("Local models are not installed. Open Drishya Settings and run Setup.") from None
    if not files or sum(f["size"] for f in files) > BUDGET:
        raise ValueError("Invalid runtime inventory.")
    for entry in files:
        check_cancel(cancel)
        if not valid_asset(safe_path(root, entry["path"]), entry):
            raise ValueError("A local runtime file is missing or corrupt. Run Setup again.")
    return True


def install_runtime(lock, runtime, cache, cancel, progress=lambda *args: None, cleanup_cache=False):
    runtime = Path(runtime)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    if sum(a["size"] for a in lock["assets"]) > BUDGET:
        raise ValueError("Runtime downloads exceed the 1 GB budget.")
    with _install_lock, installation_guard(runtime):
        check_cancel(cancel)
        recover_installation(runtime, cancel)
        try:
            verify_runtime(runtime, cancel)
            installed_lock = json.loads((runtime / "inventory.json").read_text(encoding="utf-8")).get("lock_sha256")
        except ValueError:
            installed_lock = None
        if installed_lock == lock_fingerprint(lock):
            if cleanup_cache:
                cleanup_download_cache(cache, lock)
            return
        stage = Path(tempfile.mkdtemp(prefix=runtime.name + "-staging-", dir=runtime.parent))
        backup = runtime.with_name(runtime.name + "-previous")
        try:
            for asset in lock["assets"]:
                source = download_asset(asset, cache, cancel, progress)
                if asset["kind"] == "file":
                    target = safe_path(stage, asset["destination"])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                elif asset["kind"] in ("zip", "wheel"):
                    destination = stage if asset["kind"] == "wheel" else safe_path(stage, asset["destination"])
                    extract_archive(source, destination, cancel, only_library=asset["kind"] == "wheel")
                else:
                    raise ValueError("Unknown runtime archive format.")
            check_cancel(cancel)
            write_inventory(stage, lock)
            verify_runtime(stage, cancel)
            if backup.exists():
                raise ValueError("Previous setup backup exists; close NVDA and remove the runtime-previous directory before retrying.")
            if runtime.exists():
                runtime.rename(backup)
            try:
                check_cancel(cancel)
                stage.rename(runtime)
            except Exception:
                if backup.exists():
                    backup.rename(runtime)
                raise
            if backup.exists():
                remove_owned_directory(backup, runtime.parent)
            if cleanup_cache:
                cleanup_download_cache(cache, lock)
        finally:
            if stage.exists():
                remove_owned_directory(stage, runtime.parent)

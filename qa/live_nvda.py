"""Run the installed NVDA on a private desktop for integration QA.

The user's active desktop, NVDA instance and clipboard are not used or replaced.
No system UI is automated: the test bootstrap calls this add-on's own methods.
"""
import ctypes
import argparse
from ctypes import wintypes
import json
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "qa/artifacts/nvda-profile"


class StartupInfo(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("pid", wintypes.DWORD), ("thread_id", wintypes.DWORD)]


class PrivateProcess:
    def __init__(self, executable, arguments, desktop):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = self.kernel.CreateProcessW
        create.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                           wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                           ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
        create.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        startup.lpDesktop = desktop
        info = ProcessInfo()
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(executable), *arguments]))
        if not create(str(executable), command, None, None, False, subprocess.CREATE_NO_WINDOW,
                      None, str(executable.parent), ctypes.byref(startup), ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle, self.pid = info.hProcess, info.pid
        self.kernel.CloseHandle(info.hThread)

    def poll(self):
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return None if code.value == 259 else code.value

    def wait(self, timeout):
        if self.kernel.WaitForSingleObject(self.handle, int(timeout * 1000)) == 258:
            raise subprocess.TimeoutExpired("NVDA QA", timeout)
        return self.poll()

    def terminate(self):
        self.kernel.TerminateProcess(self.handle, 1)

    def close(self):
        self.kernel.CloseHandle(self.handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["smol", "mirage"], default="mirage")
    args = parser.parse_args()
    PROFILE.mkdir(parents=True, exist_ok=True)
    result_path = PROFILE / "result.json"
    result_path.unlink(missing_ok=True)
    scratchpad = PROFILE / "scratchpad/globalPlugins"
    scratchpad.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "qa/nvda_bootstrap.py", scratchpad / "drishya_qa_bootstrap.py")
    shutil.copytree(ROOT / "addon", PROFILE / "addons/drishya", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "runtime"))
    (PROFILE / "workspace.txt").write_text(str(ROOT), encoding="utf-8")
    (PROFILE / "model-profile.txt").write_text(args.profile, encoding="ascii")
    (PROFILE / "nvda.ini").write_text("[development]\nenableScratchpadDir = True\n[general]\nshowWelcomeDialogAtStartup = False\n", encoding="utf-8")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.CreateWindowStationW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user.CreateWindowStationW.restype = wintypes.HANDLE
    user.GetProcessWindowStation.restype = wintypes.HANDLE
    user.SetProcessWindowStation.argtypes = [wintypes.HANDLE]
    user.SetProcessWindowStation.restype = wintypes.BOOL
    user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user.CreateDesktopW.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    user.CloseWindowStation.argtypes = [wintypes.HANDLE]
    station = desktop = process = None
    previous = user.GetProcessWindowStation()
    try:
        # This host denies new window stations, but permits private desktops.
        # The bootstrap therefore substitutes the clipboard sink for its Copy check.
        desktop = user.CreateDesktopW("DrishyaQA", None, None, 0, 0x02000000, None)
        if not desktop:
            raise ctypes.WinError(ctypes.get_last_error())
        executable = Path("C:/Program Files/NVDA/nvda_noUIAccess.exe")
        process = PrivateProcess(executable, ["--config-path", str(PROFILE), "--minimal", "--no-sr-flag",
                                              "--log-file", str(PROFILE / "nvda.log"), "--log-level", "10"],
                                 "winsta0\\DrishyaQA")
        deadline = time.monotonic() + 70
        while not result_path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.2)
        if not result_path.exists():
            print(json.dumps({"passed": False, "error": "No NVDA QA report", "exit_code": process.poll()}))
            raise SystemExit(1)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        (ROOT / "qa/artifacts" / ("nvda-integration-" + args.profile + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        raise SystemExit(0 if result.get("passed") else 1)
    finally:
        user.SetProcessWindowStation(previous)
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if process:
            process.close()
        if desktop:
            user.CloseDesktop(desktop)
        if station:
            user.CloseWindowStation(station)


if __name__ == "__main__":
    main()

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time
import unittest
import tests


@unittest.skipUnless(os.name == "nt", "Windows process lifetime test")
class ProcessTests(unittest.TestCase):
    def test_model_helper_does_not_survive_parent_crash(self):
        script = ("import os,sys,subprocess; import tests; from drishya.engine import hidden_process; "
                  "p=hidden_process([sys.executable,'-c','import time; time.sleep(30)'], "
                  "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
                  "print(p.pid,flush=True); os._exit(0)")
        parent = subprocess.Popen([sys.executable, "-c", script], cwd=tests.ROOT,
                                  stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        pid = int(parent.stdout.readline())
        parent.wait(timeout=5)
        parent.stdout.close()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1001, False, pid)
        if not handle:
            return
        try:
            deadline = time.monotonic() + 1
            code = wintypes.DWORD()
            while time.monotonic() < deadline:
                kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                if code.value != 259:
                    break
                time.sleep(.02)
            self.assertNotEqual(code.value, 259, "Local model survived its parent process")
        finally:
            kernel.TerminateProcess(handle, 1)
            kernel.CloseHandle(handle)

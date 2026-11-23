"""Owned local processes with bounded cancellation and authenticated loopback."""
import http.client
import json
import os
import queue
import secrets
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .assets import Cancelled, check_cancel, verify_runtime
from .protocol import parse_smol, smol_request
from .port_owner import peer_is_owned


class InferenceError(Exception):
    pass


def local_json(port, path, key, payload, cancel, timeout, owned_pid=None):
    """Use a direct socket; HTTP proxies never see screenshots or API keys."""
    check_cancel(cancel)
    result = queue.Queue(maxsize=1)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=max(timeout, 1))

    def request():
        try:
            connection.connect()
            connection.auto_open = 0  # Never reconnect after checking this exact socket.
            if owned_pid is not None and not peer_is_owned(connection.sock, owned_pid):
                raise InferenceError("The local model port belongs to another process. Please retry.")
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            connection.request("GET" if body is None else "POST", path, body, {
                "Authorization": "Bearer " + key, "Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(2 * 1024 * 1024 + 1)
            if response.status != 200:
                raise InferenceError("Local model returned HTTP " + str(response.status) + ". Try again.")
            if len(data) > 2 * 1024 * 1024:
                raise InferenceError("Local model response is too large.")
            result.put((True, json.loads(data)))
        except Exception as error:
            result.put((False, error))
        finally:
            connection.close()

    threading.Thread(target=request, daemon=True, name="Drishya HTTP").start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            check_cancel(cancel)
            if time.monotonic() >= deadline:
                raise InferenceError("Local description timed out. Try a smaller image.")
            try:
                ok, value = result.get(timeout=.05)
            except queue.Empty:
                continue
            if ok:
                return value
            if isinstance(value, InferenceError):
                raise value
            raise InferenceError("Cannot communicate with the local model. Try again.") from value
    finally:
        if connection.sock:
            try:
                connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()


@dataclass(frozen=True)
class ImageData:
    png: bytes
    rgb: bytes
    width: int
    height: int


@dataclass(frozen=True)
class Result:
    text: str
    seconds: float
    model: str


def hidden_process(command, **kwargs):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    job = None
    process = None
    try:
        if os.name == "nt":
            from .job import ProcessJob
            job = ProcessJob()
        process = subprocess.Popen(command, **options, **kwargs)
        if job:
            job.assign(process.pid)
            process.drishya_job = job
        return process
    except Exception:
        if process:
            process.terminate()
            process.wait(timeout=2)
        if job:
            job.close()
        raise


def stop_process(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream:
            stream.close()
    job = getattr(process, "drishya_job", None)
    if job:
        job.close()



class Engine:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.process = None
        self.threads = None
        self.port = 0
        self.key = ""
        self._request_lock = threading.Lock()
        self._process_lock = threading.RLock()
        self._shutdown = threading.Event()

    def close(self):
        self._shutdown.set()
        with self._process_lock:
            process, self.process = self.process, None
            self.threads = None
        stop_process(process)

    def reset(self):
        self.close()
        self._shutdown.clear()

    def _start(self, threads, cancel):
        with self._process_lock:
            if self.process and self.process.poll() is None and self.threads == threads:
                return
            stop_process(self.process)
            self.process = None
        verify_runtime(self.runtime, cancel)
        check_cancel(cancel)
        check_cancel(self._shutdown)
        executables = list((self.runtime / "llama").rglob("llama-server.exe"))
        if len(executables) != 1:
            raise InferenceError("The model runtime is missing. Download or verify it in Drishya Settings.")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.port = reservation.getsockname()[1]
        self.key = secrets.token_urlsafe(32)
        command = [str(executables[0]), "-m", str(self.runtime / "models/SmolVLM2-500M-Video-Instruct-Q8_0.gguf"),
                   "--mmproj", str(self.runtime / "models/mmproj-SmolVLM2-500M-Video-Instruct-f16.gguf"),
                   "--host", "127.0.0.1", "--port", str(self.port), "--api-key", self.key,
                   "-c", "4096", "-t", str(threads), "-np", "1", "-ngl", "0", "--no-mmproj-offload"]
        with self._process_lock:
            check_cancel(self._shutdown)
            check_cancel(cancel)
            self.process = hidden_process(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.threads = threads
            process = self.process
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            check_cancel(cancel)
            check_cancel(self._shutdown)
            if process.poll() is not None:
                raise InferenceError("The model could not start. Check the runtime files and available memory.")
            try:
                local_json(self.port, "/health", self.key, None, cancel, .5, owned_pid=process.pid)
                return
            except InferenceError:
                cancel.wait(.1)
        raise InferenceError("Model startup timed out.")

    def describe(self, image, detail, threads, cancel):
        if not self._request_lock.acquire(blocking=False):
            raise InferenceError("A description is already running.")
        started = time.monotonic()
        try:
            self._start(threads, cancel)
            text = parse_smol(local_json(self.port, "/v1/chat/completions", self.key,
                                         smol_request(image.png, detail), cancel, 90,
                                         owned_pid=self.process.pid), detail)
            check_cancel(cancel)
            check_cancel(self._shutdown)
            return Result(text, time.monotonic() - started, "SmolVLM2 500M Q8")
        except Exception:
            with self._process_lock:
                process, self.process = self.process, None
                self.threads = None
            stop_process(process)
            raise
        finally:
            self._request_lock.release()

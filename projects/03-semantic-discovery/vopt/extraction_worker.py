"""Persistent, supervised native PDF worker; no network or multiprocessing bootstrap.

The parent owns deadlines and checkpoints. A timed-out native call is terminated
with its process, never left running in an abandoned thread. One worker retains
its PDF and OCR models across successful pages; a failure starts a fresh worker.
This bounds wall time and IPC size, not the worker's total resident memory.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time

DEFAULT_PAGE_TIMEOUT_SECONDS = 120.0
MAX_RESULT_BYTES = 32 * 1024 * 1024
WORKER_SCRIPT = Path(__file__).resolve()
_NETWORK_ATTEMPTS = 0


class PageTimeoutError(TimeoutError):
    pass


class PageWorkerError(RuntimeError):
    pass


def validate_execution(isolate_pages, page_timeout_seconds):
    if type(isolate_pages) is not bool:
        raise ValueError("isolate_pages must be a boolean")
    if (type(page_timeout_seconds) not in (int, float) or not math.isfinite(page_timeout_seconds)
            or not 0 < page_timeout_seconds <= 3600):
        raise ValueError("page_timeout_seconds must be finite, greater than zero and at most 3600")


def _worker_command(source, directory):
    # Windows venv python.exe is a redirector which starts another interpreter.
    # Waiting/terminating that launcher does not supervise the native worker.
    # Launch the actual base executable, explicitly adding this environment's
    # package directories under -I instead of inheriting ambient PYTHONPATH.
    executable = getattr(sys, "_base_executable", None) if os.name == "nt" else sys.executable
    if not executable or not Path(executable).is_file():
        raise PageWorkerError("Actual Python interpreter unavailable for isolated native worker")
    package_paths = list(dict.fromkeys(str(Path(sysconfig.get_path(kind)).resolve()) for kind in ("purelib", "platlib")))
    bootstrap = ("import runpy,sys;sys.path[:0]=" + repr(package_paths)
                 + ";sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')")
    return [str(executable), "-I", "-c", bootstrap, str(WORKER_SCRIPT), source, str(directory)]


class PageProcess:
    """Single sequential child, restarted after any failed request.

    A child publishes a complete bounded JSON file atomically. Polling that file
    avoids a pipe ``recv`` blocking indefinitely after a partial large message.
    Stdout/stderr are discarded so native diagnostic output cannot fill a pipe.
    """

    def __init__(self, source, timeout_seconds=DEFAULT_PAGE_TIMEOUT_SECONDS):
        validate_execution(True, timeout_seconds)
        self.source = str(Path(source).resolve())
        self.timeout_seconds = float(timeout_seconds)
        self._scratch = tempfile.TemporaryDirectory(prefix="vopt-page-worker-")
        self._directory = Path(self._scratch.name)
        self._process = None
        self._sequence = 0
        self._closed = False
        self._unreaped = False
        self.page_count = None
        self.worker_starts = 0
        self.native_pid = None

    @property
    def pid(self):
        return self._process.pid if self._process is not None else None

    def __enter__(self):
        try:
            self._start()
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, *args):
        self.close()

    def _stop(self, graceful=False):
        process = self._process
        if process is None:
            return
        if graceful and process.poll() is None:
            # EOF lets PyMuPDF release its document/mapped handles normally.
            # A stuck native destructor is still terminated after this bound.
            if process.stdin:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired as exc:
                    # Keep the reference: never spawn a second concurrent child.
                    self._unreaped = True
                    raise PageWorkerError("Native worker could not be reaped after terminate/kill") from exc
        if process.stdin:
            process.stdin.close()
        self._process = None

    def close(self):
        if not self._closed:
            self._stop(graceful=True)
            self._scratch.cleanup()
            self._closed = True

    def _wait(self, path, deadline, operation):
        while True:
            if time.monotonic() >= deadline:
                raise PageTimeoutError(f"Native {operation} exceeded {self.timeout_seconds:g}s; worker terminated; coverage unknown")
            if path.exists():
                if path.stat().st_size > MAX_RESULT_BYTES:
                    raise PageWorkerError("Native worker result exceeds bounded IPC size")
                try:
                    result = json.loads(path.read_text(encoding="utf-8"))
                finally:
                    path.unlink(missing_ok=True)
                if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                    raise PageWorkerError("Malformed native worker response")
                if not result["ok"]:
                    error = PageWorkerError(str(result.get("error", "Unknown native worker failure"))[:2000])
                    error.network_attempts = result.get("network_attempts")
                    raise error
                return result["result"]
            exit_code = self._process.poll()
            if exit_code is not None:
                raise PageWorkerError(f"Native worker exited unexpectedly ({exit_code}); coverage unknown")
            time.sleep(min(.01, max(0, deadline - time.monotonic())))

    def _start(self, deadline=None):
        if self._closed:
            raise PageWorkerError("Native worker supervisor is closed")
        if self._unreaped:
            raise PageWorkerError("Native worker termination failed; supervisor cannot accept further pages")
        if self._process is not None:
            if self._process.poll() is None:
                return
            self._stop()
        ready = self._directory / "ready.json"
        ready.unlink(missing_ok=True)
        started = self._directory / "started.json"
        started.unlink(missing_ok=True)
        deadline = deadline or time.monotonic() + self.timeout_seconds
        command = _worker_command(self.source, self._directory)
        self._process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.worker_starts += 1
        try:
            identity = self._wait(started, deadline, "worker start")
            self.native_pid = identity.get("pid") if isinstance(identity, dict) else None
            if type(self.native_pid) is not int or self.native_pid != self._process.pid:
                raise PageWorkerError("Native worker PID differs from supervised process; interpreter launcher unsupported")
            opened = self._wait(ready, deadline, "PDF open")
            count = opened.get("page_count") if isinstance(opened, dict) else None
            if type(count) is not int or count < 1:
                raise PageWorkerError("Invalid native page count")
            if self.page_count is not None and count != self.page_count:
                raise PageWorkerError("Source page count changed while restarting native worker")
            self.page_count = count
        except BaseException as exc:
            self._stop(graceful=not isinstance(exc, (PageTimeoutError, KeyboardInterrupt, SystemExit)))
            raise

    def read_page(self, index, force_ocr):
        if type(index) is not int or index < 0 or (self.page_count is not None and index >= self.page_count):
            raise ValueError("page index outside source document")
        deadline = time.monotonic() + self.timeout_seconds
        try:
            self._start(deadline)
            self._sequence += 1
            response = self._directory / f"result-{self._sequence}.json"
            self._process.stdin.write(json.dumps({"index": index, "force_ocr": bool(force_ocr), "sequence": self._sequence}) + "\n")
            self._process.stdin.flush()
            result = self._wait(response, deadline, f"page {index + 1}")
            if not isinstance(result, dict) or result.get("page_number") != index + 1 or result.get("status") != "ok":
                raise PageWorkerError("Native worker returned wrong page or invalid status")
            result["worker_pid_verified"] = True
            return result
        except BaseException as exc:
            self._stop(graceful=not isinstance(exc, (PageTimeoutError, KeyboardInterrupt, SystemExit)))
            raise


def _block_network():
    def blocked(*args, **kwargs):
        global _NETWORK_ATTEMPTS
        _NETWORK_ATTEMPTS += 1
        raise RuntimeError("Offline native worker forbids Python network operations")
    for name in ("connect", "connect_ex", "sendto", "sendmsg"):
        if hasattr(socket.socket, name):
            setattr(socket.socket, name, blocked)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        setattr(socket, name, blocked)


def _publish(path, payload):
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        encoded = json.dumps({"ok": False, "error": "Native worker result exceeds bounded IPC size"}).encode("utf-8")
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)


def serve(source, directory):
    _block_network()
    directory = Path(directory)
    _publish(directory / "started.json", {"ok": True, "result": {"pid": os.getpid()}})
    from vopt import ingest
    import pymupdf

    pdf = None
    try:
        pdf = pymupdf.open(source)
        if pdf.needs_pass:
            raise ValueError("Encrypted PDF requires an unlocked local copy.")
        if not pdf.is_pdf or pdf.page_count == 0:
            raise ValueError("Input must be a nonempty PDF.")
        _publish(directory / "ready.json", {"ok": True, "result": {"page_count": pdf.page_count}})
    except Exception as exc:
        _publish(directory / "ready.json", {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        if pdf is not None:
            pdf.close()
        return
    with pdf:
        for message in sys.stdin:
            request = json.loads(message)
            sequence, index = request["sequence"], request["index"]
            if type(sequence) is not int or sequence < 1 or type(index) is not int or not 0 <= index < pdf.page_count:
                raise ValueError("Invalid native worker command")
            try:
                result = ingest._read_page(pdf.load_page(index), bool(request["force_ocr"]))
                result["worker_network_attempts"] = _NETWORK_ATTEMPTS
                payload = {"ok": True, "result": result}
            except Exception as exc:
                payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "network_attempts": _NETWORK_ATTEMPTS}
            _publish(directory / f"result-{sequence}.json", payload)


if __name__ == "__main__":
    # -I disables ambient PYTHONPATH/current-directory imports. Import only this
    # installed package's parent (also supports a deliberate source checkout).
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    serve(sys.argv[1], sys.argv[2])

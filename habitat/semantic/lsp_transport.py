from __future__ import annotations

import json
import queue
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_PENDING_REQUESTS = 128
DEFAULT_STDERR_TAIL_BYTES = 64 * 1024


class LspProtocolError(ValueError):
    """Raised when an inbound LSP/JSON-RPC frame violates the transport contract."""


class LspRequestTimeout(TimeoutError):
    """Raised when one LSP request exceeds its bounded response deadline."""


def encode_lsp_message(message: dict) -> bytes:
    if not isinstance(message, dict):
        raise TypeError("LSP JSON-RPC message must be an object")
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


class LspFrameDecoder:
    """Incrementally decode stdio LSP frames with a bounded JSON body."""

    def __init__(self, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES):
        if not isinstance(max_body_bytes, int) or isinstance(max_body_bytes, bool) or max_body_bytes < 0:
            raise ValueError("max_body_bytes must be a non-negative integer")
        self.max_body_bytes = max_body_bytes
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[dict]:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("LSP transport input must be bytes-like")
        self._buffer.extend(bytes(data))
        messages: list[dict] = []

        while True:
            header_end = self._buffer.find(b"\r\n\r\n")
            if header_end < 0:
                return messages

            try:
                raw_headers = bytes(self._buffer[:header_end]).decode("ascii", errors="strict")
            except UnicodeDecodeError as exc:
                raise LspProtocolError("invalid non-ASCII LSP header") from exc

            lengths: list[str] = []
            for line in raw_headers.split("\r\n") if raw_headers else []:
                name, sep, value = line.partition(":")
                if not sep:
                    raise LspProtocolError("invalid LSP header")
                if name.strip().lower() == "content-length":
                    lengths.append(value.strip())

            if len(lengths) != 1 or not lengths[0].isdigit():
                raise LspProtocolError("exactly one valid Content-Length is required")

            length = int(lengths[0])
            if length > self.max_body_bytes:
                raise LspProtocolError("LSP body exceeds configured limit")

            body_start = header_end + 4
            body_end = body_start + length
            if len(self._buffer) < body_end:
                return messages

            body = bytes(self._buffer[body_start:body_end])
            del self._buffer[:body_end]

            try:
                value = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LspProtocolError("invalid LSP JSON body") from exc
            if not isinstance(value, dict):
                raise LspProtocolError("LSP JSON-RPC message must be an object")
            messages.append(value)


@dataclass(frozen=True)
class LspServerSpec:
    provider_id: str
    languages: frozenset[str]
    argv: tuple[str, ...]
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("provider_id must be a non-empty string")
        if not self.argv or not all(isinstance(item, str) and item for item in self.argv):
            raise ValueError("argv must contain at least one non-empty string")
        if not isinstance(self.languages, frozenset) or not all(
            isinstance(item, str) and item for item in self.languages
        ):
            raise ValueError("languages must be a frozenset of non-empty strings")


_CAPABILITY_FIELDS = {
    "definition": "definitionProvider",
    "references": "referencesProvider",
    "hover": "hoverProvider",
    "document-symbols": "documentSymbolProvider",
}


class LspProcessSession:
    """Own one bounded, workspace-scoped stdio LSP subprocess."""

    def __init__(
        self,
        spec: LspServerSpec,
        root: Path,
        *,
        request_timeout_s: float = 5.0,
        initialize_timeout_s: float = 10.0,
        shutdown_timeout_s: float = 3.0,
        terminate_grace_s: float = 2.0,
        max_pending_requests: int = DEFAULT_MAX_PENDING_REQUESTS,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        stderr_tail_bytes: int = DEFAULT_STDERR_TAIL_BYTES,
    ) -> None:
        self.spec = spec
        self.root = Path(root).resolve()
        self.request_timeout_s = float(request_timeout_s)
        self.initialize_timeout_s = float(initialize_timeout_s)
        self.shutdown_timeout_s = float(shutdown_timeout_s)
        self.terminate_grace_s = float(terminate_grace_s)
        self.max_pending_requests = int(max_pending_requests)
        self.stderr_tail_bytes = int(stderr_tail_bytes)
        if min(
            self.request_timeout_s,
            self.initialize_timeout_s,
            self.shutdown_timeout_s,
            self.terminate_grace_s,
        ) <= 0:
            raise ValueError("LSP timeouts must be positive")
        if self.max_pending_requests < 1:
            raise ValueError("max_pending_requests must be positive")
        if self.stderr_tail_bytes < 0:
            raise ValueError("stderr_tail_bytes must be non-negative")

        self._decoder = LspFrameDecoder(max_body_bytes=max_body_bytes)
        self._process: subprocess.Popen[bytes] | None = None
        self._state = "NEW"
        self._failure_reason = ""
        self._capabilities: dict[str, Any] = {}
        self._next_request_id = 1
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict]] = {}
        self._notifications: deque[dict] = deque(maxlen=256)
        self._stderr_lock = threading.Lock()
        self._stderr_tail = bytearray()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._consecutive_timeouts = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def capabilities(self) -> dict[str, Any]:
        return dict(self._capabilities)

    def start(self) -> dict[str, Any]:
        if self._state != "NEW":
            raise RuntimeError(f"LSP session cannot start from state {self._state}")
        self._state = "STARTING"
        try:
            self._process = subprocess.Popen(
                list(self.spec.argv),
                cwd=str(self.root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                bufsize=0,
            )
            self._state = "INITIALIZING"
            self._stdout_thread = threading.Thread(
                target=self._stdout_loop,
                name=f"habitat-lsp-stdout-{self.spec.provider_id}",
                daemon=True,
            )
            self._stderr_thread = threading.Thread(
                target=self._stderr_loop,
                name=f"habitat-lsp-stderr-{self.spec.provider_id}",
                daemon=True,
            )
            self._stdout_thread.start()
            self._stderr_thread.start()

            result = self.request(
                "initialize",
                {
                    "processId": None,
                    "clientInfo": {"name": "nolane-habitat", "version": "0.1.0-alpha.19"},
                    "rootUri": self.root.as_uri(),
                    "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
                    "capabilities": {},
                },
                timeout_s=self.initialize_timeout_s,
            )
            if not isinstance(result, dict):
                raise RuntimeError("LSP initialize result must be an object")
            capabilities = result.get("capabilities")
            if not isinstance(capabilities, dict):
                raise RuntimeError("LSP initialize result is missing capabilities")
            self._validate_required_capabilities(capabilities)
            self._capabilities = dict(capabilities)
            self.notify("initialized", {})
            self._state = "READY"
            return dict(self._capabilities)
        except Exception as exc:
            self._fail(str(exc) or exc.__class__.__name__)
            self._terminate_process()
            raise

    def request(
        self,
        method: str,
        params: dict | None = None,
        *,
        timeout_s: float | None = None,
    ) -> Any:
        allowed = self._state == "READY" or (
            self._state == "INITIALIZING" and method == "initialize"
        ) or (self._state == "SHUTTING_DOWN" and method == "shutdown")
        if not allowed:
            raise RuntimeError(f"LSP request {method!r} is invalid in state {self._state}")
        if not isinstance(method, str) or not method:
            raise ValueError("LSP request method must be a non-empty string")
        if params is not None and not isinstance(params, dict):
            raise TypeError("LSP request params must be an object or None")

        with self._pending_lock:
            if len(self._pending) >= self.max_pending_requests:
                raise RuntimeError("LSP pending request limit reached")
            request_id = self._next_request_id
            self._next_request_id += 1
            response_queue: queue.Queue[dict] = queue.Queue(maxsize=1)
            self._pending[request_id] = response_queue

        try:
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params or {},
                }
            )
            wait_s = self.request_timeout_s if timeout_s is None else float(timeout_s)
            if wait_s <= 0:
                raise ValueError("LSP request timeout must be positive")
            try:
                response = response_queue.get(timeout=wait_s)
            except queue.Empty as exc:
                with self._pending_lock:
                    self._pending.pop(request_id, None)
                self._consecutive_timeouts += 1
                try:
                    self.notify("$/cancelRequest", {"id": request_id})
                except Exception:
                    pass
                if self._consecutive_timeouts >= 3:
                    self._fail("three consecutive LSP request timeouts")
                    self._terminate_process()
                raise LspRequestTimeout(f"LSP request timed out: {method}") from exc
        except Exception:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise

        self._consecutive_timeouts = 0
        error = response.get("error")
        if error is not None:
            raise RuntimeError(f"LSP request failed: {method}: {error}")
        return response.get("result")

    def notify(self, method: str, params: dict | None = None) -> None:
        if self._state not in {"INITIALIZING", "READY", "SHUTTING_DOWN"}:
            raise RuntimeError(f"LSP notification {method!r} is invalid in state {self._state}")
        if not isinstance(method, str) or not method:
            raise ValueError("LSP notification method must be a non-empty string")
        if params is not None and not isinstance(params, dict):
            raise TypeError("LSP notification params must be an object or None")
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def status(self) -> dict[str, Any]:
        with self._pending_lock:
            pending_count = len(self._pending)
        with self._stderr_lock:
            stderr_tail = bytes(self._stderr_tail).decode("utf-8", errors="replace")
        process = self._process
        return {
            "provider_id": self.spec.provider_id,
            "root": str(self.root),
            "state": self._state,
            "failure_reason": self._failure_reason,
            "pending_requests": pending_count,
            "consecutive_timeouts": self._consecutive_timeouts,
            "stderr_tail": stderr_tail,
            "pid": process.pid if process is not None else None,
            "returncode": process.poll() if process is not None else None,
            "capabilities": dict(self._capabilities),
        }

    def close(self) -> None:
        if self._state == "CLOSED":
            return
        if self._state == "NEW":
            self._state = "CLOSED"
            return

        if self._state == "READY":
            self._state = "SHUTTING_DOWN"
            try:
                self.request("shutdown", {}, timeout_s=self.shutdown_timeout_s)
            except Exception:
                pass
            try:
                self.notify("exit", {})
            except Exception:
                pass

        self._terminate_process(graceful_wait=self.shutdown_timeout_s)
        self._close_pipes()
        with self._pending_lock:
            self._pending.clear()
        self._state = "CLOSED"

    def _validate_required_capabilities(self, capabilities: dict[str, Any]) -> None:
        missing: list[str] = []
        for capability in sorted(self.spec.required_capabilities):
            field = _CAPABILITY_FIELDS.get(capability)
            if field is None or not capabilities.get(field):
                missing.append(capability)
        if missing:
            raise RuntimeError(
                "LSP server is missing required capabilities: " + ", ".join(missing)
            )

    def _send(self, message: dict) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("LSP process stdin is unavailable")
        wire = encode_lsp_message(message)
        try:
            with self._write_lock:
                process.stdin.write(wire)
                process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._fail(f"LSP process write failed: {exc}")
            raise RuntimeError("LSP process write failed") from exc

    def _stdout_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                try:
                    messages = self._decoder.feed(chunk)
                except Exception as exc:
                    self._fail(f"LSP protocol error: {exc}")
                    self._terminate_process()
                    return
                for message in messages:
                    self._dispatch(message)
        except Exception as exc:
            self._fail(f"LSP stdout reader failed: {exc}")
        finally:
            if self._state not in {"SHUTTING_DOWN", "CLOSED", "FAILED"}:
                self._fail("LSP process stdout closed unexpectedly")

    def _stderr_loop(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            while True:
                chunk = process.stderr.read(4096)
                if not chunk:
                    return
                if self.stderr_tail_bytes == 0:
                    continue
                with self._stderr_lock:
                    self._stderr_tail.extend(chunk)
                    if len(self._stderr_tail) > self.stderr_tail_bytes:
                        del self._stderr_tail[: len(self._stderr_tail) - self.stderr_tail_bytes]
        except Exception:
            return

    def _dispatch(self, message: dict) -> None:
        request_id = message.get("id")
        if isinstance(request_id, int) and ("result" in message or "error" in message):
            with self._pending_lock:
                target = self._pending.pop(request_id, None)
            if target is not None:
                try:
                    target.put_nowait(message)
                except queue.Full:
                    pass
            return
        if "method" in message:
            self._notifications.append(message)

    def _fail(self, reason: str) -> None:
        if self._state in {"CLOSED", "FAILED"}:
            return
        self._failure_reason = str(reason or "LSP session failed")
        self._state = "FAILED"
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        failure = {
            "jsonrpc": "2.0",
            "error": {"code": -32099, "message": self._failure_reason},
        }
        for target in pending:
            try:
                target.put_nowait(failure)
            except queue.Full:
                pass

    def _terminate_process(self, *, graceful_wait: float = 0.0) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is not None:
            return
        if graceful_wait > 0:
            try:
                process.wait(timeout=graceful_wait)
                return
            except subprocess.TimeoutExpired:
                pass
        try:
            process.terminate()
            process.wait(timeout=self.terminate_grace_s)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            process.kill()
            process.wait(timeout=self.terminate_grace_s)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _close_pipes(self) -> None:
        process = self._process
        if process is None:
            return
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass

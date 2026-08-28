from __future__ import annotations

import json


DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024


class LspProtocolError(ValueError):
    """Raised when an inbound LSP/JSON-RPC frame violates the transport contract."""


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

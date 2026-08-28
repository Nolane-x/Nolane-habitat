from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line == b"\r\n":
            break
        try:
            name, value = line.decode("ascii").rstrip("\r\n").split(":", 1)
        except Exception:
            return None
        headers[name.strip().lower()] = value.strip()
    raw_length = headers.get("content-length")
    if raw_length is None or not raw_length.isdigit():
        return None
    body = sys.stdin.buffer.read(int(raw_length))
    if len(body) != int(raw_length):
        return None
    value = json.loads(body.decode("utf-8"))
    return value if isinstance(value, dict) else None


def send(message: dict) -> None:
    body = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def append_event(path: str | None, method: str, params: dict) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"method": method, "params": params}, sort_keys=True) + "\n")
        handle.flush()


def wait_for_release(marker: str | None, release: str | None) -> None:
    if marker:
        target = Path(marker)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ready", encoding="utf-8")
    if not release:
        return
    deadline = time.monotonic() + 5.0
    release_path = Path(release)
    while not release_path.exists():
        if time.monotonic() >= deadline:
            return
        time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        default="normal",
        choices=(
            "normal",
            "initialize-error",
            "crash-after-init",
            "hang-request",
            "malformed-frame",
            "unsupported-capability",
            "stderr-spam",
            "controlled-delay",
        ),
    )
    parser.add_argument("--event-log")
    parser.add_argument("--delay-marker")
    parser.add_argument("--release-marker")
    args = parser.parse_args()
    documents: dict[str, dict] = {}
    cancellations: list[int] = []

    if args.mode == "stderr-spam":
        sys.stderr.write("x" * (96 * 1024))
        sys.stderr.flush()

    while True:
        message = read_message()
        if message is None:
            return 0
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize" and request_id is not None:
            if args.mode == "initialize-error":
                send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32002, "message": "fake initialize failure"}})
                continue
            capabilities = {
                "definitionProvider": args.mode != "unsupported-capability",
                "referencesProvider": True,
                "hoverProvider": True,
                "documentSymbolProvider": True,
                "textDocumentSync": 1,
            }
            send({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "capabilities": capabilities,
                    "serverInfo": {"name": "habitat-fake-lsp", "version": "1.0"},
                },
            })
            continue

        if method == "initialized":
            if args.mode == "crash-after-init":
                return 23
            continue

        if method == "shutdown" and request_id is not None:
            send({"jsonrpc": "2.0", "id": request_id, "result": None})
            continue

        if method == "exit":
            return 0

        if method == "$/cancelRequest":
            value = params.get("id")
            if isinstance(value, int):
                cancellations.append(value)
            continue

        if method == "textDocument/didOpen":
            append_event(args.event_log, method, params)
            doc = params.get("textDocument") or {}
            uri = str(doc.get("uri") or "")
            documents[uri] = {"version": doc.get("version"), "text": doc.get("text", "")}
            continue

        if method == "textDocument/didChange":
            append_event(args.event_log, method, params)
            doc = params.get("textDocument") or {}
            uri = str(doc.get("uri") or "")
            changes = params.get("contentChanges") or []
            text = changes[-1].get("text", "") if changes and isinstance(changes[-1], dict) else ""
            documents[uri] = {"version": doc.get("version"), "text": text}
            continue

        if method == "textDocument/didClose":
            append_event(args.event_log, method, params)
            doc = params.get("textDocument") or {}
            documents.pop(str(doc.get("uri") or ""), None)
            continue

        if request_id is None:
            continue

        # Intentionally accept the request but never answer it. Unlike sleeping, the fake server
        # keeps reading stdin so tests can observe Habitat's subsequent $/cancelRequest message.
        if args.mode == "hang-request" and method != "fake/state":
            continue

        if args.mode == "malformed-frame" and method != "fake/state":
            sys.stdout.buffer.write(b"Content-Type: application/json\r\n\r\n{}")
            sys.stdout.buffer.flush()
            continue

        if method == "textDocument/definition":
            if args.mode == "controlled-delay":
                wait_for_release(args.delay_marker, args.release_marker)
            uri = str((params.get("textDocument") or {}).get("uri") or "")
            send({"jsonrpc": "2.0", "id": request_id, "result": {"uri": uri, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 3}}}})
        elif method == "textDocument/references":
            send({"jsonrpc": "2.0", "id": request_id, "result": []})
        elif method == "textDocument/hover":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"contents": {"kind": "plaintext", "value": "fake hover"}}})
        elif method == "textDocument/documentSymbol":
            send({"jsonrpc": "2.0", "id": request_id, "result": []})
        elif method == "fake/state":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"documents": documents, "cancellations": cancellations, "pid": os.getpid()}})
        else:
            send({"jsonrpc": "2.0", "id": request_id, "result": None})


if __name__ == "__main__":
    raise SystemExit(main())

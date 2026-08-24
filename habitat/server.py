from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .protocol import MAX_REQUEST_BYTES, HabitatProtocol, PROTOCOL_VERSION, ProtocolError, parse_json_request
from .workspace import HabitatWorkspace


def _drain_wire_line(stream, chunk) -> None:
    while chunk and not chunk.endswith(b"\n" if isinstance(chunk,bytes) else "\n"):
        chunk=stream.readline(min(64 * 1024,MAX_REQUEST_BYTES + 1))


def _read_wire_line(inp) -> str | None:
    stream=getattr(inp,"buffer",None) or inp
    chunks=[]; wire_bytes=0; binary=None
    while True:
        chunk=stream.readline(max(1,MAX_REQUEST_BYTES-wire_bytes+1))
        if chunk in {"",b""}:
            break
        if not isinstance(chunk,(str,bytes)):
            raise ProtocolError("INVALID_JSON","request could not be decoded as UTF-8")
        chunk_binary=isinstance(chunk,bytes)
        if binary is None: binary=chunk_binary
        elif binary != chunk_binary:
            raise ProtocolError("INVALID_JSON","request stream changed encoding")
        chunk_bytes=len(chunk) if chunk_binary else len(chunk.encode("utf-8",errors="surrogatepass"))
        wire_bytes+=chunk_bytes
        newline=chunk.endswith(b"\n" if chunk_binary else "\n")
        if wire_bytes>MAX_REQUEST_BYTES:
            if not newline: _drain_wire_line(stream,chunk)
            raise ProtocolError("REQUEST_TOO_LARGE","request exceeds the protocol size limit")
        chunks.append(chunk)
        if newline:
            break
    if not chunks:
        return None
    if binary:
        try: return b"".join(chunks).decode("utf-8",errors="strict")
        except UnicodeDecodeError: raise ProtocolError("INVALID_JSON","request must be UTF-8") from None
    return "".join(chunks)


def _serialize_response(response: dict, workspace: HabitatWorkspace) -> str:
    try:
        return json.dumps(response,ensure_ascii=False,separators=(",",":"),allow_nan=False)
    except (TypeError,ValueError,OverflowError):
        fallback={
            "protocol":PROTOCOL_VERSION,
            "id":None,
            "ok":False,
            "revision":workspace.revision,
            "error":{
                "code":"INTERNAL_ERROR",
                "message":"response could not be serialized as strict JSON",
                "details":{},
            },
        }
        return json.dumps(fallback,ensure_ascii=False,separators=(",",":"),allow_nan=False)


def serve_stdio(workspace: HabitatWorkspace, inp=None, out=None) -> int:
    inp = inp or sys.stdin
    out = out or sys.stdout
    protocol = HabitatProtocol(workspace)
    while True:
        try:
            raw = _read_wire_line(inp)
            if raw is None: break
            if not raw.strip(): continue
            request = parse_json_request(raw)
            response = protocol.handle(request)
        except ProtocolError as exc:
            response = {
                "protocol": PROTOCOL_VERSION,
                "id": None,
                "ok": False,
                "revision": workspace.revision,
                "error": {"code": exc.code, "message": exc.message, "details": {}},
            }
        except Exception as exc:
            response = {
                "protocol": PROTOCOL_VERSION,
                "id": None,
                "ok": False,
                "revision": workspace.revision,
                "error": {"code": "INVALID_JSON", "message": "request could not be parsed", "details": {}},
            }
        out.write(_serialize_response(response,workspace) + "\n")
        out.flush()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="habitat-agent-server")
    p.add_argument("workspace")
    p.add_argument("--no-observatory",action="store_true")
    p.add_argument("--no-open-observatory",action="store_true")
    p.add_argument("--observatory-port",type=int,default=0)
    args = p.parse_args(argv)
    ws=HabitatWorkspace(Path(args.workspace))
    try:
        if not args.no_observatory:
            try:
                obs=ws.observatory_start(port=args.observatory_port,open_browser=not args.no_open_observatory)
                print(f"Habitat Observatory: {obs.get('url')}",file=sys.stderr,flush=True)
            except Exception as exc:
                print(f"Habitat Observatory failed to start: {exc}",file=sys.stderr,flush=True)
        return serve_stdio(ws)
    finally:
        ws.close()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .protocol import HabitatProtocol, PROTOCOL_VERSION, ProtocolError, parse_json_request
from .workspace import HabitatWorkspace


def serve_stdio(workspace: HabitatWorkspace, inp=None, out=None) -> int:
    inp = inp or sys.stdin
    out = out or sys.stdout
    protocol = HabitatProtocol(workspace)
    for raw in inp:
        raw = raw.strip()
        if not raw:
            continue
        try:
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
        out.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
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

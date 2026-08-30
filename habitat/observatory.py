from __future__ import annotations

import argparse
import time
from pathlib import Path

from .observability import ObservatoryReadModel
from .observatory_frontend import ObservatoryServer
from .workspace import HabitatWorkspace

__all__ = ["ObservatoryReadModel", "ObservatoryServer", "start_observatory", "main"]


def start_observatory(workspace: HabitatWorkspace, *, host: str="127.0.0.1", port: int=0, open_browser: bool=True) -> ObservatoryServer:
    return ObservatoryServer(workspace,host,port).start(open_browser=open_browser)


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog="habitat-observatory",description="Read-only real-time Nolane Habitat Observatory")
    p.add_argument("workspace")
    p.add_argument("--host",default="127.0.0.1",choices=["127.0.0.1","localhost","::1"])
    p.add_argument("--port",type=int,default=0)
    p.add_argument("--no-open",action="store_true")
    args=p.parse_args(argv)
    ws=HabitatWorkspace(Path(args.workspace)); obs=start_observatory(ws,host=args.host,port=args.port,open_browser=not args.no_open)
    print(obs.url,flush=True)
    try:
        while True: time.sleep(3600)
    except KeyboardInterrupt: pass
    finally:
        obs.close(); ws.close()
    return 0


if __name__=="__main__":
    raise SystemExit(main())

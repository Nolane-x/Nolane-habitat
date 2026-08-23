from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .database_health import inspect_database
from .workspace import HabitatWorkspace
from .model import to_dict
from . import __version__

def emit(value): print(json.dumps(to_dict(value),indent=2,ensure_ascii=False))

def main(argv=None):
    p=argparse.ArgumentParser(prog="habitat",description="Nolane Habitat human/operator compatibility CLI")
    p.add_argument("--version",action="version",version=__version__)
    sub=p.add_subparsers(dest="cmd",required=True)
    sp=sub.add_parser("create"); sp.add_argument("source"); sp.add_argument("workspace"); sp.add_argument("--backend",choices=["local","mirror"],default="local")
    sp=sub.add_parser("enter"); sp.add_argument("workspace")
    sp=sub.add_parser("doctor"); sp.add_argument("workspace")
    sp=sub.add_parser("backend-info"); sp.add_argument("workspace")
    sp=sub.add_parser("capabilities"); sp.add_argument("workspace")
    sp=sub.add_parser("refresh"); sp.add_argument("workspace")
    sp=sub.add_parser("orient"); sp.add_argument("workspace"); sp.add_argument("task"); sp.add_argument("--budget",type=int,default=18)
    sp=sub.add_parser("context-page"); sp.add_argument("workspace"); sp.add_argument("handle"); sp.add_argument("--offset",type=int,default=0); sp.add_argument("--limit",type=int,default=20)
    sp=sub.add_parser("query"); sp.add_argument("workspace"); sp.add_argument("query"); sp.add_argument("--limit",type=int,default=20)
    sp=sub.add_parser("inspect"); sp.add_argument("workspace"); sp.add_argument("object_id"); sp.add_argument("--source",choices=["none","body","range","full"],default="none")
    sp=sub.add_parser("source-read"); sp.add_argument("workspace"); sp.add_argument("path"); sp.add_argument("--start-line",type=int,default=1); sp.add_argument("--max-lines",type=int,default=200)
    sp=sub.add_parser("replace-text"); sp.add_argument("workspace"); sp.add_argument("path"); sp.add_argument("old"); sp.add_argument("new")
    sp=sub.add_parser("stage-replace-text"); sp.add_argument("workspace"); sp.add_argument("path"); sp.add_argument("old"); sp.add_argument("new")
    sp=sub.add_parser("stage-symbol"); sp.add_argument("workspace"); sp.add_argument("symbol_id"); sp.add_argument("new_source")
    sp=sub.add_parser("stage-rename"); sp.add_argument("workspace"); sp.add_argument("symbol_id"); sp.add_argument("new_name")
    sp=sub.add_parser("commit"); sp.add_argument("workspace"); sp.add_argument("transaction")
    sp=sub.add_parser("rollback"); sp.add_argument("workspace"); sp.add_argument("transaction")
    sp=sub.add_parser("run"); sp.add_argument("workspace"); sp.add_argument("capability"); sp.add_argument("--timeout",type=int,default=60)
    sp=sub.add_parser("verify-plan"); sp.add_argument("workspace"); sp.add_argument("paths",nargs="*")
    sp=sub.add_parser("checkpoint"); sp.add_argument("workspace"); sp.add_argument("task"); sp.add_argument("objects",nargs="+")
    sp=sub.add_parser("resume"); sp.add_argument("workspace"); sp.add_argument("session")
    sp=sub.add_parser("ui-observe"); sp.add_argument("workspace"); sp.add_argument("path")
    sp=sub.add_parser("policy-status"); sp.add_argument("workspace")
    sp=sub.add_parser("execution-security"); sp.add_argument("workspace")
    sp=sub.add_parser("git-status"); sp.add_argument("workspace")
    sp=sub.add_parser("git-history"); sp.add_argument("workspace"); sp.add_argument("--path"); sp.add_argument("--limit",type=int,default=20)
    sp=sub.add_parser("dependencies"); sp.add_argument("workspace"); sp.add_argument("--query")
    sp=sub.add_parser("agent-open"); sp.add_argument("workspace"); sp.add_argument("name")
    sp=sub.add_parser("lease-status"); sp.add_argument("workspace"); sp.add_argument("--agent-id")
    args=p.parse_args(argv)
    try:
        if args.cmd=="doctor":
            report=inspect_database(Path(args.workspace) / "habitat.sqlite3")
            emit(report)
            return 0 if report["ok"] else 1
        if args.cmd=="create":
            ws=HabitatWorkspace.create(args.source,args.workspace,backend=args.backend); emit(ws.enter()); ws.close(); return 0
        ws=HabitatWorkspace(Path(args.workspace))
        try:
            if args.cmd=="enter": emit(ws.enter())
            elif args.cmd=="backend-info": emit(ws.backend_info())
            elif args.cmd=="capabilities": emit(ws.capability_report())
            elif args.cmd=="refresh": emit(ws.refresh())
            elif args.cmd=="orient": emit(ws.orient(args.task,args.budget))
            elif args.cmd=="context-page": emit(ws.context_page(args.handle,args.offset,args.limit))
            elif args.cmd=="query": emit(ws.query(args.query,args.limit))
            elif args.cmd=="inspect": emit(ws.inspect(args.object_id,args.source))
            elif args.cmd=="source-read": emit(ws.read_source(args.path,args.start_line,args.max_lines))
            elif args.cmd=="replace-text": emit(ws.change([{"op":"replace_text","path":args.path,"old":args.old,"new":args.new}]))
            elif args.cmd=="stage-replace-text": emit(ws.stage_change([{"op":"replace_text","path":args.path,"old":args.old,"new":args.new}]))
            elif args.cmd=="stage-symbol": emit(ws.stage_symbol_change(args.symbol_id,args.new_source))
            elif args.cmd=="stage-rename": emit(ws.stage_symbol_rename(args.symbol_id,args.new_name))
            elif args.cmd=="commit": emit(ws.commit_change(args.transaction))
            elif args.cmd=="rollback": emit(ws.rollback_change(args.transaction))
            elif args.cmd=="run": emit(ws.run(args.capability,args.timeout))
            elif args.cmd=="verify-plan": emit(ws.verification_plan(changed_paths=args.paths))
            elif args.cmd=="checkpoint": emit(ws.checkpoint(args.task,args.objects))
            elif args.cmd=="resume": emit(ws.resume(args.session))
            elif args.cmd=="ui-observe": emit(ws.observe_ui(args.path))
            elif args.cmd=="policy-status": emit(ws.policy_status())
            elif args.cmd=="execution-security": emit(ws.execution_security())
            elif args.cmd=="git-status": emit(ws.git_status())
            elif args.cmd=="git-history": emit(ws.git_history(args.path,args.limit))
            elif args.cmd=="dependencies": emit(ws.dependencies_query(args.query) if args.query else ws.dependencies_snapshot())
            elif args.cmd=="agent-open": emit(ws.agent_open(args.name))
            elif args.cmd=="lease-status": emit(ws.lease_status(args.agent_id))
            return 0
        finally: ws.close()
    except Exception as exc:
        print(json.dumps({"error":type(exc).__name__,"message":str(exc)},ensure_ascii=False),file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())

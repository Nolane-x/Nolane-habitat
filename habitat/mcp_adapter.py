from __future__ import annotations

import argparse
import atexit
from pathlib import Path
from typing import Any

from .workspace import HabitatWorkspace

MCP_SPEC_TARGET = "2026-07-28"


def tool_catalog() -> list[dict[str, Any]]:
    """Compact high-level MCP surface.

    Habitat's internal protocol intentionally has many precise operations. Exposing all of them as MCP
    tools would increase tool-selection context and error surface. This catalog composes common agent
    loops into a small set while preserving the lower-level protocol for advanced clients.
    """
    return [
        {"name":"habitat_start_task","purpose":"Orient to a task, open a provenance-bound work episode, and fault a bounded exact-source packet."},
        {"name":"habitat_context_step","purpose":"Submit bounded context feedback, plan next virtual pages, and fault only selected exact source."},
        {"name":"habitat_inspect","purpose":"Inspect one semantic object with optional exact source."},
        {"name":"habitat_references","purpose":"Get resolved references and provenance for a semantic object."},
        {"name":"habitat_change_symbol","purpose":"Transactionally replace one exact symbol body and sync canonical source."},
        {"name":"habitat_rename_symbol","purpose":"Fail-closed project-wide Python semantic rename using proven references."},
        {"name":"habitat_verify","purpose":"Run graph-targeted verification and return a structured receipt."},
        {"name":"habitat_ui_open","purpose":"Open a project UI as semantic runtime state rather than pixels."},
        {"name":"habitat_ui_act","purpose":"Act on a semantic UI handle and return state delta."},
        {"name":"habitat_ui_assert","purpose":"Assert runtime UI state without screenshot interpretation."},
        {"name":"habitat_checkpoint","purpose":"Create a provenance-bound resumable checkpoint."},
        {"name":"habitat_resume","purpose":"Validate a checkpoint and choose direct, selective-revalidate, or reorient."},
    ]


def compose_start_task(ws: HabitatWorkspace, task: str, budget: int = 14, source_budget: int = 20_000, agent_id: str | None = None) -> dict:
    ws.activity_emit("agent.task.started","agent",agent_id=agent_id,status="running",summary=f"oriented task: {task[:120]}",data={"task":task,"budget":budget})
    ctx = ws.orient(task, budget, agent_id=agent_id)
    episode = ws.episode_start(task, ctx.handle)
    private_residency = ws.agent_residency_admit(agent_id, ctx.handle, max_admit=min(8,budget), pin_top=0) if agent_id else None
    abstain = bool((ctx.decision_packet or {}).get("abstention_recommended"))
    packet = ({"handle":ctx.handle,"revision":ws.revision,"pages":[],"source_bytes":0,"faults":[],
               "abstained":True,"reason":"low retrieval confidence; exact source prefetch suppressed"}
              if abstain else ws.context_prefetch(ctx.handle, max_source_bytes=source_budget, max_pages=min(8,budget)))
    notifications = ws.agent_notifications(agent_id, "pending", 20) if agent_id else None
    ws.activity_emit("agent.task.context-ready","cognition",agent_id=agent_id,episode_id=episode["id"],ref_id=ctx.handle,status="ready",summary="bounded context ready",data={"abstained":abstain,"source_bytes":packet.get("source_bytes",0),"handle":ctx.handle})
    return {"context": ctx, "source_packet": packet, "revision": ws.revision, "abstained": abstain,
            "episode_id":episode["id"], "agent_id":agent_id, "agent_residency":private_residency, "coordination_notifications":notifications,
            "cognitive_next":ws.cognition_next(agent_id,episode["id"]),
            "policy": "orientation → episode → agent-private residency → bounded context VM; whole-file dump disabled by default"}

def compose_context_step(ws: HabitatWorkspace, handle: str, *, fetched_page_ids: list[str] | None = None,
                         used_object_ids: list[str] | None = None, unhelpful_object_ids: list[str] | None = None,
                         revalidate_notification_ids: list[str] | None = None,
                         max_pages: int = 3, source_budget: int = 20_000, agent_id: str | None = None) -> dict:
    revalidated=[]
    if revalidate_notification_ids:
        if not agent_id: raise ValueError("agent_id is required for coordination revalidation")
        revalidated=[ws.agent_revalidate_notification(agent_id,nid) for nid in revalidate_notification_ids]
    feedback=None
    if used_object_ids or unhelpful_object_ids:
        feedback=ws.context_feedback(handle,used_object_ids or [],unhelpful_object_ids or [],agent_id=agent_id)
    plan=ws.context_plan_next(handle,fetched_page_ids or [],max_pages=max_pages,max_estimated_bytes=source_budget)
    ids=list(plan.get("page_ids") or [])
    fetched=ws.context_fetch_pages(handle,ids,max_source_bytes=source_budget) if ids else {"handle":handle,"pages":[],"source_bytes":0,"faults":[],"plan":plan}
    notifications=ws.agent_notifications(agent_id,"pending",20) if agent_id else None
    return {"revalidated":revalidated,"feedback":feedback,"plan":plan,"source_packet":fetched,"revision":ws.revision,"coordination_notifications":notifications}

def compose_change_symbol(ws: HabitatWorkspace, symbol_id: str, new_source: str, *, verify: bool = True, episode_id: str | None = None, agent_id: str | None = None) -> dict:
    staged=ws.stage_symbol_change(symbol_id,new_source,episode_id,agent_id)
    committed=ws.commit_change(staged["id"],agent_id)
    result={"status":"COMMITTED","committed":True,"transaction":committed,"episode_id":episode_id}
    if verify:
        try:
            # The old symbol ID may legitimately disappear after a replacement/rename. Verify by the
            # committed changed paths so post-commit validation cannot turn success into an ambiguous error.
            result["verification"]=ws.verify(changed_paths=committed.get("changed_paths") or [],episode_id=episode_id)
            result["status"]="COMMITTED_VERIFIED"
        except Exception as exc:
            result["status"]="COMMITTED_VERIFICATION_ERROR"
            result["verification_error"]={"type":type(exc).__name__,"message":str(exc)}
    return result


def build_server(workspace_path: str | Path, *, auto_observatory: bool = False, open_observatory: bool = True, observatory_port: int = 0):
    try:
        from mcp.server import MCPServer  # MCP Python SDK v2
    except Exception as exc:
        raise RuntimeError('MCP SDK v2 is optional. Install with: pip install "nolane-habitat[mcp]"') from exc

    ws = HabitatWorkspace(Path(workspace_path))
    mcp_agent_id=ws.agent_open("mcp-fallback",{"surface":"mcp","spec_target":MCP_SPEC_TARGET,"identity_mode":"explicit-handle-preferred"})["id"]
    if auto_observatory:
        try: ws.observatory_start(port=observatory_port,open_browser=open_observatory)
        except Exception as exc: ws.activity_emit("observatory.start-failed","observatory",status="failed",summary="Observatory auto-start failed",data={"error":str(exc)})
    atexit.register(ws.close)
    mcp = MCPServer("Nolane Habitat")

    def use_agent(value: str | None) -> str:
        aid=value or mcp_agent_id
        if not ws.store.agent_session(aid): raise KeyError(aid)
        return aid

    def observed_call(name: str, aid: str, fn, *, observe: bool = True):
        if not observe:
            return fn()
        ws.activity_emit("tool.started","tool",agent_id=aid,ref_id=name,status="running",summary=name)
        try:
            result=fn(); ws.activity_emit("tool.completed","tool",agent_id=aid,ref_id=name,status="passed",summary=name+" completed")
            return result
        except Exception as exc:
            ws.activity_emit("tool.completed","tool",agent_id=aid,ref_id=name,status="failed",summary=name+" failed",data={"error":type(exc).__name__,"message":str(exc)})
            raise

    @mcp.tool()
    def habitat_start_task(task: str, budget: int = 14, source_budget: int = 20000, agent_id: str | None = None, agent_name: str = "mcp-agent") -> dict:
        """Orient to one coding task. If no agent handle is supplied, mint one and return it for stateless follow-up calls."""
        aid=agent_id
        if aid is None:
            aid=ws.agent_open(agent_name,{"surface":"mcp","spec_target":MCP_SPEC_TARGET,"identity_mode":"explicit-handle"})["id"]
        else:
            aid=use_agent(aid)
        return observed_call("habitat_start_task",aid,lambda: compose_start_task(ws, task, budget, source_budget, aid))

    @mcp.tool()
    def habitat_context_step(handle: str, fetched_page_ids: list[str] | None = None, used_object_ids: list[str] | None = None, unhelpful_object_ids: list[str] | None = None, revalidate_notification_ids: list[str] | None = None, max_pages: int = 3, source_budget: int = 20000, agent_id: str | None = None) -> dict:
        """Advance virtual context memory, optionally revalidating coordination invalidations first."""
        aid=use_agent(agent_id); return observed_call("habitat_context_step",aid,lambda: compose_context_step(ws,handle,fetched_page_ids=fetched_page_ids,used_object_ids=used_object_ids,unhelpful_object_ids=unhelpful_object_ids,revalidate_notification_ids=revalidate_notification_ids,max_pages=max_pages,source_budget=source_budget,agent_id=aid))

    @mcp.tool()
    def habitat_inspect(object_id: str, include_source: str = "body", agent_id: str | None = None) -> dict:
        """Inspect one semantic object; source may be none, body, or exact supported by Habitat."""
        aid=use_agent(agent_id); return observed_call("habitat_inspect",aid,lambda: ws.inspect_snapshot(object_id, include_source),observe=False)

    @mcp.tool()
    def habitat_references(object_id: str, limit: int = 200, agent_id: str | None = None) -> dict:
        """Return project references with role, provider, trust, and source anchors."""
        aid=use_agent(agent_id); return observed_call("habitat_references",aid,lambda: ws.references_snapshot(object_id, limit),observe=False)

    @mcp.tool()
    def habitat_change_symbol(symbol_id: str, new_source: str, verify: bool = True, episode_id: str | None = None, agent_id: str | None = None) -> dict:
        """Commit one exact symbol replacement with explicit post-side-effect outcome semantics."""
        aid=use_agent(agent_id); return observed_call("habitat_change_symbol",aid,lambda: compose_change_symbol(ws,symbol_id,new_source,verify=verify,episode_id=episode_id,agent_id=aid))

    @mcp.tool()
    def habitat_rename_symbol(symbol_id: str, new_name: str, verify: bool = True, episode_id: str | None = None, agent_id: str | None = None) -> dict:
        """Commit a proven semantic rename and distinguish commit success from verification failure."""
        aid=use_agent(agent_id)
        staged=ws.stage_symbol_rename(symbol_id,new_name,episode_id,aid)
        committed=ws.commit_change(staged["id"],aid)
        result={"status":"COMMITTED","committed":True,"transaction":committed,"semantic_rename":staged.get("semantic_rename"),"episode_id":episode_id}
        if verify:
            try:
                result["verification"]=ws.verify(changed_paths=committed.get("changed_paths") or [],episode_id=episode_id); result["status"]="COMMITTED_VERIFIED"
            except Exception as exc:
                result["status"]="COMMITTED_VERIFICATION_ERROR"; result["verification_error"]={"type":type(exc).__name__,"message":str(exc)}
        ws.activity_emit("tool.completed","tool",agent_id=aid,episode_id=episode_id,ref_id="habitat_rename_symbol",status="passed" if result.get("committed") else "failed",summary="habitat_rename_symbol completed",data={"status":result.get("status")})
        return result

    @mcp.tool()
    def habitat_verify(object_ids: list[str] | None = None, changed_paths: list[str] | None = None, timeout_s: int = 60, episode_id: str | None = None, agent_id: str | None = None) -> dict:
        """Run graph-targeted verification and return structured test evidence."""
        aid=use_agent(agent_id); return observed_call("habitat_verify",aid,lambda: ws.verify(changed_paths, object_ids, timeout_s, episode_id))

    @mcp.tool()
    def habitat_ui_open(target: str, agent_id: str | None = None) -> dict:
        """Open project HTML/web UI and return DOM/accessibility/layout semantic state."""
        aid=use_agent(agent_id); return observed_call("habitat_ui_open",aid,lambda: ws.open_ui_runtime(target))

    @mcp.tool()
    def habitat_ui_act(session_id: str, action: str, handle: str, value: str | None = None, agent_id: str | None = None) -> dict:
        """Act on one semantic UI handle; coordinates are not accepted."""
        aid=use_agent(agent_id); return observed_call("habitat_ui_act",aid,lambda: ws.act_ui_runtime(session_id, action, handle, value))

    @mcp.tool()
    def habitat_ui_assert(session_id: str, assertions: list[dict], agent_id: str | None = None) -> dict:
        """Assert semantic runtime UI properties without using pixels as the primary oracle."""
        aid=use_agent(agent_id); return observed_call("habitat_ui_assert",aid,lambda: ws.assert_ui_runtime(session_id, assertions))

    @mcp.tool()
    def habitat_checkpoint(task: str, next_action: str | None = None, agent_id: str | None = None) -> dict:
        """Create a revision/provider/Merkle/residency-bound checkpoint."""
        aid=use_agent(agent_id); return observed_call("habitat_checkpoint",aid,lambda: ws.checkpoint(task, next_action=next_action))

    @mcp.tool()
    def habitat_resume(session_id: str, agent_id: str | None = None) -> dict:
        """Validate checkpoint bindings before continuation."""
        aid=use_agent(agent_id); return observed_call("habitat_resume",aid,lambda: ws.resume(session_id))

    @mcp.resource("habitat://status")
    def habitat_status() -> dict:
        return {"revision":ws.revision,"workspace":ws.enter(),"mcp_spec_target":MCP_SPEC_TARGET,"agent_id":mcp_agent_id,"notifications":ws.agent_notifications(mcp_agent_id,"pending",20),"agent_residency":ws.agent_residency_status(mcp_agent_id),"execution_security":ws.execution_security(),"observatory":ws.observatory_status(),"semantic_fabric":ws.semantic_fabric()}

    return mcp, ws


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Run Nolane Habitat as an MCP stdio server")
    parser.add_argument("workspace", help="Path to an existing Habitat workspace")
    parser.add_argument("--no-observatory",action="store_true",help="Do not auto-start the read-only realtime Observatory")
    parser.add_argument("--no-open-observatory",action="store_true",help="Start Observatory without opening a browser")
    parser.add_argument("--observatory-port",type=int,default=0,help="Loopback Observatory port; 0 chooses a free port")
    args=parser.parse_args(argv)
    mcp, _ws = build_server(args.workspace,auto_observatory=not args.no_observatory,open_observatory=not args.no_open_observatory,observatory_port=args.observatory_port)
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

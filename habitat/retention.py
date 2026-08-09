from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RetentionPolicy:
    max_trace_calls: int = 5000
    max_context_faults: int = 10000
    max_resolved_evidence: int = 5000
    max_closed_agents: int = 1000
    max_acked_notifications: int = 5000
    vacuum: bool = False

    def validate(self) -> None:
        for k,v in asdict(self).items():
            if k == "vacuum":
                continue
            if not isinstance(v,int) or isinstance(v,bool) or v < 0 or v > 10_000_000:
                raise ValueError(f"{k} must be an integer in [0,10000000]")


def _count(conn, sql: str, args=()) -> int:
    return int(conn.execute(sql,args).fetchone()[0])


def _excess(total: int, limit: int) -> int:
    return max(0,total-limit)


def plan(store, policy: RetentionPolicy) -> dict[str, Any]:
    policy.validate(); c=store.conn
    totals={
        "trace_calls":_count(c,"SELECT COUNT(*) FROM trace_calls"),
        "context_faults":_count(c,"SELECT COUNT(*) FROM context_faults"),
        "resolved_evidence":_count(c,"SELECT COUNT(*) FROM evidence WHERE active=0"),
        "closed_agents":_count(c,"SELECT COUNT(*) FROM agent_sessions WHERE status='closed'"),
        "acked_notifications":_count(c,"SELECT COUNT(*) FROM agent_notifications WHERE status='acked'"),
    }
    deletable={
        "trace_calls":_excess(totals["trace_calls"],policy.max_trace_calls),
        "context_faults":_excess(totals["context_faults"],policy.max_context_faults),
        "resolved_evidence":_excess(totals["resolved_evidence"],policy.max_resolved_evidence),
        "closed_agents":_excess(totals["closed_agents"],policy.max_closed_agents),
        "acked_notifications":_excess(totals["acked_notifications"],policy.max_acked_notifications),
    }
    return {
        "policy":asdict(policy),"totals":totals,"deletable":deletable,"would_delete":sum(deletable.values()),
        "protected_classes":["revisions","transactions","active evidence","open work episodes","active agents","pending notifications","hypotheses/experiments"],
        "claim_boundary":"Alpha.10 compaction bounds selected append-only operational history. It is not a legal-compliance retention engine and does not encrypt SQLite at rest.",
    }


def compact(store, policy: RetentionPolicy, *, dry_run: bool = True) -> dict[str, Any]:
    p=plan(store,policy)
    if dry_run:
        return {**p,"dry_run":True,"deleted":{k:0 for k in p["deletable"]}}
    c=store.conn; deleted={}
    specs=[
        ("trace_calls","seq",None),
        ("context_faults","seq",None),
        ("resolved_evidence","created_at","active=0"),
        ("closed_agents","updated_at","status='closed'"),
        ("acked_notifications","created_at","status='acked'"),
    ]
    table_map={"resolved_evidence":"evidence","closed_agents":"agent_sessions","acked_notifications":"agent_notifications"}
    for key,order,where in specs:
        n=int(p["deletable"][key]); table=table_map.get(key,key)
        if n<=0:
            deleted[key]=0; continue
        clause=f" WHERE {where}" if where else ""
        # rowid deletion works for all selected SQLite tables and avoids assuming PK shape.
        cur=c.execute(f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table}{clause} ORDER BY {order} ASC LIMIT ?)",(n,))
        deleted[key]=int(cur.rowcount or 0)
    c.commit()
    if policy.vacuum:
        c.execute("VACUUM")
    return {**plan(store,policy),"dry_run":False,"deleted":deleted,"deleted_total":sum(deleted.values())}


def harden_state_permissions(habitat_dir: Path) -> dict[str,Any]:
    habitat_dir=habitat_dir.resolve(); changed=[]; unsupported=[]
    if os.name == "nt":
        return {"changed":[],"unsupported":["POSIX mode hardening unavailable on Windows"],"claim_boundary":"Windows ACL hardening is not implemented."}
    try:
        os.chmod(habitat_dir,0o700); changed.append({"path":str(habitat_dir),"mode":"0700"})
    except OSError as exc:
        unsupported.append(str(exc))
    for name in ("habitat.sqlite3","habitat.sqlite3-wal","habitat.sqlite3-shm","workspace.json","policy.json"):
        p=habitat_dir/name
        if not p.exists(): continue
        try:
            os.chmod(p,0o600); changed.append({"path":str(p),"mode":"0600"})
        except OSError as exc:
            unsupported.append(f"{name}: {exc}")
    return {"changed":changed,"unsupported":unsupported,"claim_boundary":"POSIX permission hardening reduces accidental local exposure; it is not encryption at rest or multi-user ACL policy."}

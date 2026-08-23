from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .sql_safety import quote_identifier


_COMPACTION_RULES = frozenset(
    {
        ("trace_calls", "seq", None),
        ("context_faults", "seq", None),
        ("evidence", "created_at", "active=0"),
        ("agent_sessions", "updated_at", "status='closed'"),
        ("agent_notifications", "created_at", "status='acked'"),
    }
)
_COMPACTION_TABLES = frozenset(rule[0] for rule in _COMPACTION_RULES)
_COMPACTION_ORDER_COLUMNS = frozenset(rule[1] for rule in _COMPACTION_RULES)


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


def _compaction_delete_sql(table: str, order_column: str, where: str | None) -> str:
    """Build a deletion query solely from the fixed retention policy metadata."""

    if (table, order_column, where) not in _COMPACTION_RULES:
        raise ValueError("unsupported retention compaction rule")
    table_name = quote_identifier(table, _COMPACTION_TABLES)
    order_name = quote_identifier(order_column, _COMPACTION_ORDER_COLUMNS)
    clause = f" WHERE {where}" if where else ""
    return (
        f"DELETE FROM {table_name} WHERE rowid IN "
        f"(SELECT rowid FROM {table_name}{clause} ORDER BY {order_name} ASC LIMIT ?)"
    )


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
        ("trace_calls", "trace_calls", "seq", None),
        ("context_faults", "context_faults", "seq", None),
        ("resolved_evidence", "evidence", "created_at", "active=0"),
        ("closed_agents", "agent_sessions", "updated_at", "status='closed'"),
        ("acked_notifications", "agent_notifications", "created_at", "status='acked'"),
    ]
    for key, table, order, where in specs:
        n=int(p["deletable"][key])
        if n<=0:
            deleted[key]=0; continue
        # rowid deletion works for all selected SQLite tables and avoids assuming PK shape.
        cur=c.execute(_compaction_delete_sql(table, order, where), (n,))
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

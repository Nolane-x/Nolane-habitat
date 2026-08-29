from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage import Store


class RuntimeRepository:
    def __init__(self, owner: "Store") -> None:
        self.owner = owner

    def append(self, value: dict) -> None:
        self.owner.conn.execute(
            """INSERT INTO runtime_events(id,trace_id,span_id,parent_span_id,kind,name,status,path,symbol_id,agent_id,episode_id,revision,started_at,duration_ms,attributes_json,source)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                value["id"],
                value.get("trace_id"),
                value.get("span_id"),
                value.get("parent_span_id"),
                value.get("kind") or "runtime",
                value.get("name") or "runtime-event",
                value.get("status") or "observed",
                value.get("path"),
                value.get("symbol_id"),
                value.get("agent_id"),
                value.get("episode_id"),
                value.get("revision") or "none",
                value.get("started_at") or "",
                value.get("duration_ms"),
                json.dumps(value.get("attributes") or {}, sort_keys=True),
                value.get("source") or "runtime",
            ),
        )
        self.owner.conn.commit()

    def by_id(self, event_id: str):
        return self.owner.conn.execute("SELECT * FROM runtime_events WHERE id=?", (event_id,)).fetchone()

    def list(self, *, trace_id: str | None = None, agent_id: str | None = None, limit: int = 500):
        where = []
        args = []
        if trace_id is not None:
            where.append("trace_id=?")
            args.append(trace_id)
        if agent_id is not None:
            where.append("agent_id=?")
            args.append(agent_id)
        sql = "SELECT * FROM runtime_events" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY started_at DESC LIMIT ?"
        return self.owner.conn.execute(sql, (*args, int(limit))).fetchall()

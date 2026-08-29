from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage import Store


class LearningRepository:
    def __init__(self, owner: "Store") -> None:
        self.owner = owner

    def record_context_feedback(
        self,
        handle: str,
        object_id: str,
        verdict: str,
        weight: float,
        task_terms: list[str],
        revision: str,
        created_at: str,
    ) -> int:
        if verdict not in {"used", "unhelpful"}:
            raise ValueError("context feedback verdict must be used or unhelpful")
        cur = self.owner.conn.execute(
            "INSERT INTO context_feedback(handle,object_id,verdict,weight,task_terms_json,revision,created_at) VALUES(?,?,?,?,?,?,?)",
            (handle, object_id, verdict, float(weight), json.dumps(sorted(set(task_terms))), revision, created_at),
        )
        useful = float(weight) if verdict == "used" else 0.0
        unhelpful = float(weight) if verdict == "unhelpful" else 0.0
        for term in sorted(set(task_terms)):
            self.owner.conn.execute(
                """INSERT INTO context_utility(object_id,term,useful_weight,unhelpful_weight,last_revision,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(object_id,term) DO UPDATE SET
                     useful_weight=MIN(10.0, context_utility.useful_weight*0.92+excluded.useful_weight),
                     unhelpful_weight=MIN(10.0, context_utility.unhelpful_weight*0.92+excluded.unhelpful_weight),
                     last_revision=excluded.last_revision,updated_at=excluded.updated_at""",
                (object_id, term, useful, unhelpful, revision, created_at),
            )
        self.owner.conn.commit()
        return int(cur.lastrowid)

    def context_utility_for(self, object_id: str, terms: list[str]) -> dict:
        terms = sorted(set(t for t in terms if t))
        if not terms:
            return {"useful_weight": 0.0, "unhelpful_weight": 0.0, "matched_terms": []}
        marks = ",".join("?" for _ in terms)
        rows = self.owner.conn.execute(
            f"SELECT term,useful_weight,unhelpful_weight FROM context_utility WHERE object_id=? AND term IN ({marks})",
            [object_id, *terms],
        ).fetchall()
        return {
            "useful_weight": sum(float(r["useful_weight"]) for r in rows),
            "unhelpful_weight": sum(float(r["unhelpful_weight"]) for r in rows),
            "matched_terms": [r["term"] for r in rows],
        }

    def context_feedback_for_handle(self, handle: str, limit: int = 500):
        return self.owner.conn.execute(
            "SELECT * FROM context_feedback WHERE handle=? ORDER BY seq ASC LIMIT ?", (handle, int(limit))
        ).fetchall()

    def create_epistemic_item(self, value: dict) -> None:
        self.owner.conn.execute(
            """INSERT INTO epistemic_items(id,kind,statement,status,confidence,scope,agent_id,episode_id,base_revision,provenance_json,invalidation_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"], value["kind"], value["statement"], value["status"], value.get("confidence"), value.get("scope") or "workspace",
             value.get("agent_id"), value.get("episode_id"), value["base_revision"], json.dumps(value.get("provenance") or {}, sort_keys=True),
             json.dumps(value.get("invalidation_conditions") or [], sort_keys=True), value["created_at"], value["updated_at"]),
        )
        self.owner.conn.commit()

    def epistemic_item(self, item_id: str):
        return self.owner.conn.execute("SELECT * FROM epistemic_items WHERE id=?", (item_id,)).fetchone()

    def epistemic_items(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        limit: int = 200,
    ):
        where = []
        args = []
        if kind is not None:
            where.append("kind=?")
            args.append(kind)
        if status is not None:
            where.append("status=?")
            args.append(status)
        if agent_id is not None:
            where.append("(agent_id IS NULL OR agent_id=?)")
            args.append(agent_id)
        sql = "SELECT * FROM epistemic_items" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY updated_at DESC LIMIT ?"
        return self.owner.conn.execute(sql, (*args, int(limit))).fetchall()

    def update_epistemic_item(
        self,
        item_id: str,
        *,
        status: str | None = None,
        confidence: float | None = None,
        updated_at: str,
        provenance: dict | None = None,
    ) -> None:
        row = self.epistemic_item(item_id)
        if not row:
            raise KeyError(item_id)
        values = {
            "status": status if status is not None else row["status"],
            "confidence": confidence if confidence is not None else row["confidence"],
            "provenance_json": json.dumps(provenance, sort_keys=True) if provenance is not None else row["provenance_json"],
        }
        self.owner.conn.execute(
            "UPDATE epistemic_items SET status=?,confidence=?,provenance_json=?,updated_at=? WHERE id=?",
            (values["status"], values["confidence"], values["provenance_json"], updated_at, item_id),
        )
        self.owner.conn.commit()

    def create_project_memory(self, value: dict) -> None:
        self.owner.conn.execute(
            """INSERT INTO project_memories(id,kind,statement,status,scope,agent_id,episode_id,base_revision,confidence,provenance_json,evidence_json,valid_until_revision,supersedes,invalidated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"], value["kind"], value["statement"], value.get("status", "active"), value.get("scope", "workspace"), value.get("agent_id"),
             value.get("episode_id"), value["base_revision"], value.get("confidence"), json.dumps(value.get("provenance") or {}, ensure_ascii=False),
             json.dumps(value.get("evidence_ids") or [], ensure_ascii=False), value.get("valid_until_revision"), value.get("supersedes"),
             value.get("invalidated_by"), value["created_at"], value["updated_at"]),
        )
        self.owner.conn.commit()

    def project_memory(self, memory_id: str):
        return self.owner.conn.execute("SELECT * FROM project_memories WHERE id=?", (memory_id,)).fetchone()

    def find_active_memory(self, kind: str, statement: str, agent_id: str | None, base_revision: str):
        if agent_id is None:
            return self.owner.conn.execute(
                "SELECT * FROM project_memories WHERE kind=? AND statement=? AND agent_id IS NULL AND base_revision=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
                (kind, statement, base_revision),
            ).fetchone()
        return self.owner.conn.execute(
            "SELECT * FROM project_memories WHERE kind=? AND statement=? AND agent_id=? AND base_revision=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
            (kind, statement, agent_id, base_revision),
        ).fetchone()

    def project_memories(
        self,
        *,
        kind: str | None = None,
        status: str | None = "active",
        agent_id: str | None = None,
        limit: int = 200,
    ):
        sql = "SELECT * FROM project_memories WHERE 1=1"
        args = []
        if kind is not None:
            sql += " AND kind=?"
            args.append(kind)
        if status is not None:
            sql += " AND status=?"
            args.append(status)
        if agent_id is not None:
            sql += " AND (agent_id=? OR agent_id IS NULL)"
            args.append(agent_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(int(limit))
        return self.owner.conn.execute(sql, tuple(args)).fetchall()

    def update_project_memory(
        self,
        memory_id: str,
        *,
        status: str | None = None,
        confidence: float | None = None,
        invalidated_by: str | None = None,
        updated_at: str,
    ) -> None:
        row = self.project_memory(memory_id)
        if not row:
            raise KeyError(memory_id)
        self.owner.conn.execute(
            "UPDATE project_memories SET status=?,confidence=?,invalidated_by=?,updated_at=? WHERE id=?",
            (status if status is not None else row["status"], confidence if confidence is not None else row["confidence"],
             invalidated_by if invalidated_by is not None else row["invalidated_by"], updated_at, memory_id),
        )
        self.owner.conn.commit()

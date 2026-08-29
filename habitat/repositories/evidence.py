from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage import Store


class EvidenceRepository:
    def __init__(self, owner: "Store") -> None:
        self.owner = owner

    def append(self, value: dict) -> None:
        self.owner.conn.execute(
            """INSERT OR REPLACE INTO evidence(id,kind,revision,path,object_id,severity,summary,trust,source,data_json,created_at,active)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                value["id"],
                value["kind"],
                value["revision"],
                value.get("path"),
                value.get("object_id"),
                value.get("severity", "info"),
                value["summary"],
                value.get("trust", "derived"),
                value.get("source", "workspace"),
                json.dumps(value.get("data", {}), separators=(",", ":")),
                value["created_at"],
                int(value.get("active", True)),
            ),
        )
        self.owner.delete_search(value["id"])
        self.owner.index_search(value["id"], "evidence", value.get("path") or "", value["summary"], value["summary"])

    def by_id(self, evidence_id: str):
        return self.owner.conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()

    def active(self, kind: str | None = None, limit: int = 500):
        if kind:
            return self.owner.conn.execute(
                "SELECT * FROM evidence WHERE active=1 AND kind=? ORDER BY created_at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        return self.owner.conn.execute(
            "SELECT * FROM evidence WHERE active=1 ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def active_ids(
        self,
        *,
        kind: str | None = None,
        paths: list[str] | None = None,
        object_ids: list[str] | None = None,
        source: str | None = None,
    ) -> list[str]:
        clauses = ["active=1"]
        args = []
        if kind:
            clauses.append("kind=?")
            args.append(kind)
        if source:
            clauses.append("source=?")
            args.append(source)
        selectors = []
        if paths:
            selectors.append("path IN (%s)" % ",".join("?" for _ in paths))
            args.extend(paths)
        if object_ids:
            selectors.append("object_id IN (%s)" % ",".join("?" for _ in object_ids))
            args.extend(object_ids)
        if selectors:
            clauses.append("(" + " OR ".join(selectors) + ")")
        return [
            row["id"]
            for row in self.owner.conn.execute(
                "SELECT id FROM evidence WHERE " + " AND ".join(clauses) + " ORDER BY created_at,id",
                tuple(args),
            ).fetchall()
        ]

    def by_ids(self, ids: list[str]):
        ids = [object_id for object_id in ids if object_id]
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        return self.owner.conn.execute(f"SELECT * FROM evidence WHERE id IN ({marks})", ids).fetchall()

    def resolve(
        self,
        *,
        kind: str | None = None,
        paths: list[str] | None = None,
        object_ids: list[str] | None = None,
        source: str | None = None,
    ) -> int:
        clauses = ["active=1"]
        args = []
        if kind:
            clauses.append("kind=?")
            args.append(kind)
        if source:
            clauses.append("source=?")
            args.append(source)
        selectors = []
        if paths:
            selectors.append("path IN (%s)" % ",".join("?" for _ in paths))
            args.extend(paths)
        if object_ids:
            selectors.append("object_id IN (%s)" % ",".join("?" for _ in object_ids))
            args.extend(object_ids)
        if selectors:
            clauses.append("(" + " OR ".join(selectors) + ")")
        cursor = self.owner.conn.execute(
            "UPDATE evidence SET active=0 WHERE " + " AND ".join(clauses), tuple(args)
        )
        return int(cursor.rowcount or 0)

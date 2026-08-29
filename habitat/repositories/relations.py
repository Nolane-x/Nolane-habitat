from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ..model import RelationRecord

if TYPE_CHECKING:
    from ..storage import Store


class RelationsRepository:
    def __init__(self, owner: "Store") -> None:
        self.owner = owner

    def replace(self, relations: Iterable[RelationRecord]) -> None:
        self.owner.conn.execute("DELETE FROM relations")
        for relation in relations:
            self.owner.conn.execute(
                "INSERT OR REPLACE INTO relations(source_id,target_id,kind,trust,evidence) VALUES(?,?,?,?,?)",
                (relation.source_id, relation.target_id, relation.kind, relation.trust, relation.evidence),
            )

    def sync(self, relations: Iterable[RelationRecord]) -> dict:
        """Set-diff the project relation graph and write only changed edges."""
        incoming = {(relation.source_id, relation.target_id, relation.kind): relation for relation in relations}
        current_rows = self.owner.conn.execute("SELECT * FROM relations").fetchall()
        current = {(row["source_id"], row["target_id"], row["kind"]): row for row in current_rows}
        inserted = updated = unchanged = 0
        for key, relation in incoming.items():
            row = current.get(key)
            if row is None:
                self.owner.conn.execute(
                    "INSERT INTO relations(source_id,target_id,kind,trust,evidence) VALUES(?,?,?,?,?)",
                    (relation.source_id, relation.target_id, relation.kind, relation.trust, relation.evidence),
                )
                inserted += 1
            elif row["trust"] != relation.trust or row["evidence"] != relation.evidence:
                self.owner.conn.execute(
                    "UPDATE relations SET trust=?,evidence=? WHERE source_id=? AND target_id=? AND kind=?",
                    (relation.trust, relation.evidence, relation.source_id, relation.target_id, relation.kind),
                )
                updated += 1
            else:
                unchanged += 1
        deleted_keys = set(current) - set(incoming)
        if deleted_keys:
            self.owner.conn.executemany(
                "DELETE FROM relations WHERE source_id=? AND target_id=? AND kind=?",
                list(deleted_keys),
            )
        return {
            "inserted": inserted,
            "updated": updated,
            "deleted": len(deleted_keys),
            "unchanged": unchanged,
            "total": len(incoming),
        }

    def for_object(self, object_id: str):
        return self.owner.conn.execute(
            "SELECT * FROM relations WHERE source_id=? OR target_id=?", (object_id, object_id)
        ).fetchall()

    def incoming(self, object_id: str, kind: str | None = None):
        if kind:
            return self.owner.conn.execute(
                "SELECT * FROM relations WHERE target_id=? AND kind=?", (object_id, kind)
            ).fetchall()
        return self.owner.conn.execute("SELECT * FROM relations WHERE target_id=?", (object_id,)).fetchall()

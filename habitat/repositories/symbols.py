from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable

from ..model import SymbolRecord

if TYPE_CHECKING:
    from ..storage import Store


def _index_terms(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value or "").replace("_", " ").replace("-", " ")
    return sorted(
        {
            term.casefold()
            for term in re.findall(r"\w+", value, flags=re.UNICODE)
            if len(term) >= 2 and not term.isdigit()
        }
    )


class SymbolsRepository:
    def __init__(self, owner: "Store") -> None:
        self.owner = owner

    def replace_for_file(self, file_id: str, symbols: Iterable[SymbolRecord]) -> None:
        old_ids = [r[0] for r in self.owner.conn.execute("SELECT id FROM symbols WHERE file_id=?", (file_id,))]
        for oid in old_ids:
            self.owner.conn.execute("DELETE FROM relations WHERE source_id=? OR target_id=?", (oid, oid))
            self.owner.delete_search(oid)
        self.owner.conn.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
        for symbol in symbols:
            self.owner.conn.execute(
                """INSERT INTO symbols(id,file_id,path,name,qualified_name,kind,language,start_line,end_line,signature,summary,trust)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol.id,
                    symbol.file_id,
                    symbol.path,
                    symbol.name,
                    symbol.qualified_name,
                    symbol.kind,
                    symbol.language,
                    symbol.start_line,
                    symbol.end_line,
                    symbol.signature,
                    symbol.summary,
                    symbol.trust,
                ),
            )
            body = " ".join(filter(None, [symbol.signature, symbol.summary]))
            self.owner.index_search(symbol.id, "symbol", symbol.path, symbol.qualified_name, body)
            for term in _index_terms(symbol.qualified_name + " " + symbol.path):
                self.owner.conn.execute(
                    "INSERT OR IGNORE INTO symbol_terms(term,symbol_id,path) VALUES(?,?,?)",
                    (term, symbol.id, symbol.path),
                )

    def matching_terms(self, terms: list[str], limit: int = 1000):
        """Bounded indexed candidate retrieval; avoids scanning every symbol for every task."""
        if not terms or limit < 1:
            return []
        ids = []
        seen = set()
        for raw in terms[:64]:
            term = str(raw).casefold()
            if not term:
                continue
            prefixes = [term]
            if len(term) >= 7:
                prefixes.append(term[:-1] if term.endswith("s") else term)
                for suffix in ("ation", "tion", "ment", "ing", "ed", "ity", "ness"):
                    if term.endswith(suffix) and len(term) - len(suffix) >= 4:
                        prefixes.append(term[: -len(suffix)])
            clauses = []
            args = []
            for prefix in dict.fromkeys(prefixes):
                clauses.append("term=? OR term LIKE ?")
                args.extend([prefix, prefix + "%"] if len(prefix) >= 4 else [prefix, prefix])
            sql = "SELECT DISTINCT symbol_id FROM symbol_terms WHERE " + " OR ".join(
                f"({clause})" for clause in clauses
            ) + " LIMIT ?"
            rows = self.owner.conn.execute(sql, [*args, min(250, int(limit))]).fetchall()
            for row in rows:
                object_id = row["symbol_id"]
                if object_id not in seen:
                    seen.add(object_id)
                    ids.append(object_id)
                    if len(ids) >= limit:
                        break
            if len(ids) >= limit:
                break
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = self.owner.conn.execute(f"SELECT * FROM symbols WHERE id IN ({marks})", ids).fetchall()
        by_id = {row["id"]: row for row in rows}
        return [by_id[object_id] for object_id in ids if object_id in by_id]

    def by_id(self, object_id: str):
        return self.owner.conn.execute("SELECT * FROM symbols WHERE id=?", (object_id,)).fetchone()

    def named(self, name: str):
        query = f"%{name.lower()}%"
        return self.owner.conn.execute(
            "SELECT * FROM symbols WHERE lower(name) LIKE ? OR lower(qualified_name) LIKE ? LIMIT 100",
            (query, query),
        ).fetchall()

    def for_file(self, file_id: str):
        return self.owner.conn.execute("SELECT * FROM symbols WHERE file_id=? ORDER BY start_line", (file_id,)).fetchall()

    def all(self):
        return self.owner.conn.execute("SELECT * FROM symbols ORDER BY path,start_line").fetchall()

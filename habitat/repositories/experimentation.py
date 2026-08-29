from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage import Store


class ExperimentationRepository:
    def __init__(self, owner: "Store") -> None:
        self.owner = owner

    def create_hypothesis(self, value: dict) -> None:
        self.owner.conn.execute(
            """INSERT INTO hypotheses(id,episode_id,task,statement,status,prior_confidence,current_confidence,base_revision,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (value["id"], value.get("episode_id"), value["task"], value["statement"], value.get("status", "active"),
             float(value.get("prior_confidence", 0.5)), float(value.get("current_confidence", value.get("prior_confidence", 0.5))),
             value["base_revision"], value["created_at"], value.get("updated_at", value["created_at"])),
        )
        self.owner.conn.commit()

    def hypothesis(self, hypothesis_id: str):
        return self.owner.conn.execute("SELECT * FROM hypotheses WHERE id=?", (hypothesis_id,)).fetchone()

    def hypotheses(self, episode_id: str | None = None, status: str | None = None, limit: int = 100):
        clauses = []
        args = []
        if episode_id is not None:
            clauses.append("episode_id=?")
            args.append(episode_id)
        if status is not None:
            clauses.append("status=?")
            args.append(status)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return self.owner.conn.execute(
            f"SELECT * FROM hypotheses{where} ORDER BY updated_at DESC LIMIT ?", [*args, int(limit)]
        ).fetchall()

    def update_hypothesis(
        self,
        hypothesis_id: str,
        *,
        status: str | None = None,
        confidence: float | None = None,
        updated_at: str,
    ) -> None:
        row = self.hypothesis(hypothesis_id)
        if not row:
            raise KeyError(hypothesis_id)
        self.owner.conn.execute(
            "UPDATE hypotheses SET status=?,current_confidence=?,updated_at=? WHERE id=?",
            (status or row["status"], float(row["current_confidence"] if confidence is None else confidence), updated_at, hypothesis_id),
        )
        self.owner.conn.commit()

    def link_hypothesis_evidence(
        self,
        hypothesis_id: str,
        evidence_id: str | None,
        polarity: str,
        weight: float,
        note: str | None,
        revision: str,
        created_at: str,
    ) -> int:
        if not self.hypothesis(hypothesis_id):
            raise KeyError(hypothesis_id)
        cur = self.owner.conn.execute(
            "INSERT INTO hypothesis_evidence(hypothesis_id,evidence_id,polarity,weight,note,revision,created_at) VALUES(?,?,?,?,?,?,?)",
            (hypothesis_id, evidence_id, polarity, float(weight), note, revision, created_at),
        )
        self.owner.conn.commit()
        return int(cur.lastrowid)

    def hypothesis_evidence(self, hypothesis_id: str):
        return self.owner.conn.execute(
            "SELECT * FROM hypothesis_evidence WHERE hypothesis_id=? ORDER BY seq", (hypothesis_id,)
        ).fetchall()

    def create_experiment(self, value: dict) -> None:
        self.owner.conn.execute(
            """INSERT INTO experiments(id,hypothesis_id,episode_id,description,discriminator,status,capability,expected_json,result_json,base_revision,created_at,completed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"], value.get("hypothesis_id"), value.get("episode_id"), value["description"], value.get("discriminator"),
             value.get("status", "planned"), value.get("capability"), json.dumps(value.get("expected") or {}, sort_keys=True),
             json.dumps(value.get("result") or {}, sort_keys=True), value["base_revision"], value["created_at"], value.get("completed_at")),
        )
        self.owner.conn.commit()

    def experiment(self, experiment_id: str):
        return self.owner.conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()

    def experiments_for_hypothesis(self, hypothesis_id: str, limit: int = 100):
        return self.owner.conn.execute(
            "SELECT * FROM experiments WHERE hypothesis_id=? ORDER BY created_at LIMIT ?", (hypothesis_id, int(limit))
        ).fetchall()

    def complete_experiment(self, experiment_id: str, status: str, result: dict, completed_at: str) -> None:
        cur = self.owner.conn.execute(
            "UPDATE experiments SET status=?,result_json=?,completed_at=? WHERE id=?",
            (status, json.dumps(result or {}, sort_keys=True), completed_at, experiment_id),
        )
        if cur.rowcount != 1:
            raise KeyError(experiment_id)
        self.owner.conn.commit()

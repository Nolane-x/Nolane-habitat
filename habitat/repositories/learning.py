from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..learning_plane import ContextPolicy, EvaluationPacket, OutcomeRecord, PolicyCandidate
from ..learning_plane.model import _thaw_json_value

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

    # --- Foundation Convergence Wave 5: Learning Plane persistence ---
    def create_policy_version(
        self,
        policy: ContextPolicy,
        *,
        parent_version: str | None,
        created_by: str,
        created_at: str,
    ) -> None:
        if not isinstance(policy, ContextPolicy):
            raise TypeError("policy must be ContextPolicy")
        if parent_version is not None and self.policy_version(parent_version) is None:
            raise KeyError(parent_version)
        self.owner.conn.execute(
            """INSERT INTO learning_policy_versions(version,fingerprint,policy_json,parent_version,created_by,created_at)
               VALUES(?,?,?,?,?,?)""",
            (
                policy.version,
                policy.fingerprint,
                json.dumps(policy.canonical_payload, sort_keys=True, separators=(",", ":")),
                parent_version,
                created_by,
                created_at,
            ),
        )
        self.owner.conn.commit()

    def policy_version(self, version: str):
        return self.owner.conn.execute(
            "SELECT * FROM learning_policy_versions WHERE version=?",
            (version,),
        ).fetchone()

    def policy_versions(self, limit: int = 500):
        return self.owner.conn.execute(
            "SELECT * FROM learning_policy_versions ORDER BY created_at ASC,version ASC LIMIT ?",
            (int(limit),),
        ).fetchall()

    def create_candidate(self, candidate: PolicyCandidate) -> None:
        if not isinstance(candidate, PolicyCandidate):
            raise TypeError("candidate must be PolicyCandidate")
        policy = self.policy_version(candidate.policy_version)
        baseline = self.policy_version(candidate.baseline_version)
        if policy is None:
            raise KeyError(candidate.policy_version)
        if baseline is None:
            raise KeyError(candidate.baseline_version)
        if policy["fingerprint"] != candidate.policy_fingerprint:
            raise ValueError("candidate policy fingerprint does not match immutable policy version")
        if baseline["fingerprint"] != candidate.baseline_fingerprint:
            raise ValueError("candidate baseline fingerprint does not match immutable policy version")
        self.owner.conn.execute(
            """INSERT INTO learning_candidates(candidate_id,policy_version,policy_fingerprint,baseline_version,baseline_fingerprint,generator_id,state,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                candidate.candidate_id,
                candidate.policy_version,
                candidate.policy_fingerprint,
                candidate.baseline_version,
                candidate.baseline_fingerprint,
                candidate.generator_id,
                candidate.state,
                candidate.created_at,
                candidate.updated_at,
            ),
        )
        self.owner.conn.commit()

    def candidate(self, candidate_id: str):
        return self.owner.conn.execute(
            "SELECT * FROM learning_candidates WHERE candidate_id=?",
            (candidate_id,),
        ).fetchone()

    def update_candidate_state(
        self,
        candidate_id: str,
        *,
        expected_state: str,
        new_state: str,
        updated_at: str,
    ) -> None:
        current = self.candidate(candidate_id)
        if current is None:
            raise KeyError(candidate_id)
        if current["state"] != expected_state:
            raise ValueError(
                f"candidate state changed: expected {expected_state}, found {current['state']}"
            )
        cursor = self.owner.conn.execute(
            """UPDATE learning_candidates SET state=?,updated_at=?
               WHERE candidate_id=? AND state=?""",
            (new_state, updated_at, candidate_id, expected_state),
        )
        if cursor.rowcount != 1:
            self.owner.conn.rollback()
            raise ValueError("candidate state changed concurrently")
        self.owner.conn.commit()

    def append_outcome(self, candidate_id: str, outcome: OutcomeRecord) -> int:
        if not isinstance(outcome, OutcomeRecord):
            raise TypeError("outcome must be OutcomeRecord")
        candidate = self.candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate["policy_version"] != outcome.policy_version:
            raise ValueError("outcome policy version does not match candidate")
        cursor = self.owner.conn.execute(
            """INSERT INTO learning_outcomes(
                 candidate_id,policy_version,task_fingerprint,benchmark_class,
                 provider_fingerprints_json,context_refs_json,action_refs_json,verification_refs_json,
                 independent_outcome_json,resource_metrics_json,errors_json,rollbacks_json,revision,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                candidate_id,
                outcome.policy_version,
                outcome.task_fingerprint,
                outcome.benchmark_class,
                json.dumps(outcome.provider_fingerprints, separators=(",", ":")),
                json.dumps(outcome.context_refs, separators=(",", ":")),
                json.dumps(outcome.action_refs, separators=(",", ":")),
                json.dumps(outcome.verification_refs, separators=(",", ":")),
                json.dumps(_thaw_json_value(outcome.independent_outcome), sort_keys=True, separators=(",", ":")),
                json.dumps(dict(outcome.resource_metrics), sort_keys=True, separators=(",", ":")),
                json.dumps(outcome.errors, separators=(",", ":")),
                json.dumps(outcome.rollbacks, separators=(",", ":")),
                outcome.revision,
                outcome.created_at,
            ),
        )
        self.owner.conn.commit()
        return int(cursor.lastrowid)

    def outcomes(self, candidate_id: str, limit: int = 1000):
        return self.owner.conn.execute(
            "SELECT * FROM learning_outcomes WHERE candidate_id=? ORDER BY id ASC LIMIT ?",
            (candidate_id, int(limit)),
        ).fetchall()

    def append_evaluation(
        self,
        candidate_id: str,
        packet: EvaluationPacket,
        *,
        created_at: str,
    ) -> int:
        if not isinstance(packet, EvaluationPacket):
            raise TypeError("packet must be EvaluationPacket")
        candidate = self.candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if packet.candidate_id != candidate_id:
            raise ValueError("evaluation candidate identity mismatch")
        if packet.policy_fingerprint != candidate["policy_fingerprint"]:
            raise ValueError("evaluation policy fingerprint does not match candidate")
        cursor = self.owner.conn.execute(
            """INSERT INTO learning_evaluations(
                 candidate_id,policy_fingerprint,evaluator_id,heldout_suite_id,
                 baseline_benchmark_fingerprint,candidate_benchmark_fingerprint,improved,
                 evidence_refs_json,reproduction_tolerance,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                candidate_id,
                packet.policy_fingerprint,
                packet.evaluator_id,
                packet.heldout_suite_id,
                packet.baseline_benchmark_fingerprint,
                packet.candidate_benchmark_fingerprint,
                int(packet.improved),
                json.dumps(packet.evidence_refs, separators=(",", ":")),
                packet.reproduction_tolerance,
                created_at,
            ),
        )
        self.owner.conn.commit()
        return int(cursor.lastrowid)

    def evaluations(self, candidate_id: str, limit: int = 1000):
        return self.owner.conn.execute(
            "SELECT * FROM learning_evaluations WHERE candidate_id=? ORDER BY id ASC LIMIT ?",
            (candidate_id, int(limit)),
        ).fetchall()

    def latest_evaluation(self, candidate_id: str):
        return self.owner.conn.execute(
            "SELECT * FROM learning_evaluations WHERE candidate_id=? ORDER BY id DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()

    def append_activation(
        self,
        *,
        candidate_id: str,
        action: str,
        previous_version: str | None,
        previous_fingerprint: str | None,
        active_version: str,
        active_fingerprint: str,
        evaluation_id: int,
        baseline_benchmark_fingerprint: str,
        candidate_benchmark_fingerprint: str,
        reproduction_benchmark_fingerprint: str | None,
        reproduction_tolerance: float | None,
        created_at: str,
    ) -> int:
        candidate = self.candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        evaluation = self.owner.conn.execute(
            "SELECT * FROM learning_evaluations WHERE id=?",
            (int(evaluation_id),),
        ).fetchone()
        if evaluation is None or evaluation["candidate_id"] != candidate_id:
            raise ValueError("activation evaluation does not belong to candidate")
        active = self.policy_version(active_version)
        if active is None:
            raise KeyError(active_version)
        if active["fingerprint"] != active_fingerprint:
            raise ValueError("activation fingerprint does not match immutable policy version")
        cursor = self.owner.conn.execute(
            """INSERT INTO learning_activations(
                 candidate_id,action,previous_version,previous_fingerprint,active_version,active_fingerprint,
                 evaluation_id,baseline_benchmark_fingerprint,candidate_benchmark_fingerprint,
                 reproduction_benchmark_fingerprint,reproduction_tolerance,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                candidate_id,
                action,
                previous_version,
                previous_fingerprint,
                active_version,
                active_fingerprint,
                int(evaluation_id),
                baseline_benchmark_fingerprint,
                candidate_benchmark_fingerprint,
                reproduction_benchmark_fingerprint,
                reproduction_tolerance,
                created_at,
            ),
        )
        self.owner.conn.commit()
        return int(cursor.lastrowid)

    def activations(self, candidate_id: str, limit: int = 1000):
        return self.owner.conn.execute(
            "SELECT * FROM learning_activations WHERE candidate_id=? ORDER BY id ASC LIMIT ?",
            (candidate_id, int(limit)),
        ).fetchall()

    def active_context_policy_version(self) -> str | None:
        row = self.owner.conn.execute(
            "SELECT value FROM learning_state WHERE key='active_context_policy_version'"
        ).fetchone()
        return None if row is None else row["value"]

    def set_active_context_policy_version(
        self,
        version: str | None,
        *,
        updated_at: str,
    ) -> None:
        self.owner.conn.execute(
            """INSERT INTO learning_state(key,value,updated_at)
               VALUES('active_context_policy_version',?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            (version, updated_at),
        )
        self.owner.conn.commit()
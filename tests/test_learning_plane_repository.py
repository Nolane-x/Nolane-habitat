from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from habitat.learning_plane import ContextPolicy, EvaluationPacket, OutcomeRecord, PolicyCandidate
from habitat.storage import SCHEMA_VERSION, Store


LEARNING_TABLES = {
    "learning_policy_versions",
    "learning_candidates",
    "learning_outcomes",
    "learning_evaluations",
    "learning_activations",
    "learning_state",
}


def make_policy(version: str, *, graph_depth: int = 2) -> ContextPolicy:
    return ContextPolicy(
        version=version,
        lexical_weight=1.0,
        structural_weight=1.0,
        evidence_weight=1.0,
        graph_depth=graph_depth,
        max_roots=8,
        source_prefetch_budget=18,
        abstention_threshold=0.28,
    )


def make_candidate(candidate: ContextPolicy, baseline: ContextPolicy) -> PolicyCandidate:
    return PolicyCandidate(
        candidate_id="cand-001",
        policy_version=candidate.version,
        policy_fingerprint=candidate.fingerprint,
        baseline_version=baseline.version,
        baseline_fingerprint=baseline.fingerprint,
        generator_id="generator-v1",
        state="candidate",
        created_at="2026-08-29T14:20:00Z",
        updated_at="2026-08-29T14:20:00Z",
    )


def make_outcome(policy_version: str, suffix: str = "1") -> OutcomeRecord:
    return OutcomeRecord(
        policy_version=policy_version,
        task_fingerprint=f"task:{suffix}",
        benchmark_class="semantic navigation",
        provider_fingerprints=("provider:a",),
        context_refs=(f"context:{suffix}",),
        action_refs=(f"action:{suffix}",),
        verification_refs=(f"verify:{suffix}",),
        independent_outcome={"success": suffix != "0", "score": 0.75},
        resource_metrics={"tool_calls": 0, "provider_calls": None},
        errors=(),
        rollbacks=(),
        revision=f"revision:{suffix}",
        created_at=f"2026-08-29T14:2{suffix}:00Z",
    )


def make_evaluation(candidate: ContextPolicy, suffix: str = "1") -> EvaluationPacket:
    return EvaluationPacket(
        candidate_id="cand-001",
        policy_fingerprint=candidate.fingerprint,
        evaluator_id="independent-evaluator-v1",
        heldout_suite_id="learning-heldout-v1",
        baseline_benchmark_fingerprint=("b" if suffix == "1" else "d") * 64,
        candidate_benchmark_fingerprint=("c" if suffix == "1" else "e") * 64,
        improved=True,
        evidence_refs=(f"evaluation:{suffix}",),
        reproduction_tolerance=0.0,
    )


class LearningPlaneRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "habitat.sqlite3"
        self.store = Store(self.db_path)
        self.repo = self.store._learning_repository()
        self.baseline = make_policy("context-v1")
        self.candidate_policy = make_policy("context-v2", graph_depth=3)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _insert_policies_and_candidate(self) -> PolicyCandidate:
        self.repo.create_policy_version(
            self.baseline,
            parent_version=None,
            created_by="bootstrap",
            created_at="2026-08-29T14:18:00Z",
        )
        self.repo.create_policy_version(
            self.candidate_policy,
            parent_version=self.baseline.version,
            created_by="generator-v1",
            created_at="2026-08-29T14:19:00Z",
        )
        candidate = make_candidate(self.candidate_policy, self.baseline)
        self.repo.create_candidate(candidate)
        return candidate

    def test_current_schema_contains_exact_learning_plane_tables(self):
        self.assertEqual(23, SCHEMA_VERSION)
        tables = {
            row[0]
            for row in self.store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue(LEARNING_TABLES <= tables)

    def test_policy_versions_are_immutable_and_ordered(self):
        self.repo.create_policy_version(
            self.baseline,
            parent_version=None,
            created_by="bootstrap",
            created_at="2026-08-29T14:18:00Z",
        )
        self.repo.create_policy_version(
            self.candidate_policy,
            parent_version=self.baseline.version,
            created_by="generator-v1",
            created_at="2026-08-29T14:19:00Z",
        )

        row = self.repo.policy_version("context-v1")
        self.assertIsNotNone(row)
        self.assertEqual(self.baseline.fingerprint, row["fingerprint"])
        self.assertEqual(self.baseline.canonical_payload, json.loads(row["policy_json"]))
        self.assertIsNone(row["parent_version"])

        rows = self.repo.policy_versions()
        self.assertEqual(["context-v1", "context-v2"], [row["version"] for row in rows])

        changed_same_version = make_policy("context-v1", graph_depth=4)
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create_policy_version(
                changed_same_version,
                parent_version=None,
                created_by="other",
                created_at="2026-08-29T14:30:00Z",
            )
        after = self.repo.policy_version("context-v1")
        self.assertEqual(self.baseline.fingerprint, after["fingerprint"])
        self.assertEqual(self.baseline.canonical_payload, json.loads(after["policy_json"]))

    def test_candidate_state_update_is_optimistic_not_a_hidden_lifecycle_engine(self):
        candidate = self._insert_policies_and_candidate()
        row = self.repo.candidate(candidate.candidate_id)
        self.assertEqual("candidate", row["state"])

        self.repo.update_candidate_state(
            candidate.candidate_id,
            expected_state="candidate",
            new_state="shadow",
            updated_at="2026-08-29T14:21:00Z",
        )
        self.assertEqual("shadow", self.repo.candidate(candidate.candidate_id)["state"])

        with self.assertRaisesRegex(ValueError, "state"):
            self.repo.update_candidate_state(
                candidate.candidate_id,
                expected_state="candidate",
                new_state="promoted",
                updated_at="2026-08-29T14:22:00Z",
            )
        self.assertEqual("shadow", self.repo.candidate(candidate.candidate_id)["state"])

    def test_outcomes_evaluations_and_activations_are_append_only_and_ordered(self):
        candidate = self._insert_policies_and_candidate()

        outcome_1 = self.repo.append_outcome(candidate.candidate_id, make_outcome("context-v2", "1"))
        outcome_2 = self.repo.append_outcome(candidate.candidate_id, make_outcome("context-v2", "2"))
        self.assertLess(outcome_1, outcome_2)
        outcomes = self.repo.outcomes(candidate.candidate_id)
        self.assertEqual([outcome_1, outcome_2], [row["id"] for row in outcomes])
        self.assertEqual(0, json.loads(outcomes[0]["resource_metrics_json"])["tool_calls"])
        self.assertIsNone(json.loads(outcomes[0]["resource_metrics_json"])["provider_calls"])

        evaluation_1 = self.repo.append_evaluation(
            candidate.candidate_id,
            make_evaluation(self.candidate_policy, "1"),
            created_at="2026-08-29T14:23:00Z",
        )
        evaluation_2 = self.repo.append_evaluation(
            candidate.candidate_id,
            make_evaluation(self.candidate_policy, "2"),
            created_at="2026-08-29T14:24:00Z",
        )
        self.assertLess(evaluation_1, evaluation_2)
        self.assertEqual(evaluation_2, self.repo.latest_evaluation(candidate.candidate_id)["id"])

        activation_1 = self.repo.append_activation(
            candidate_id=candidate.candidate_id,
            action="promote",
            previous_version=self.baseline.version,
            previous_fingerprint=self.baseline.fingerprint,
            active_version=self.candidate_policy.version,
            active_fingerprint=self.candidate_policy.fingerprint,
            evaluation_id=evaluation_2,
            baseline_benchmark_fingerprint="d" * 64,
            candidate_benchmark_fingerprint="e" * 64,
            reproduction_benchmark_fingerprint=None,
            reproduction_tolerance=None,
            created_at="2026-08-29T14:25:00Z",
        )
        activation_2 = self.repo.append_activation(
            candidate_id=candidate.candidate_id,
            action="rollback",
            previous_version=self.candidate_policy.version,
            previous_fingerprint=self.candidate_policy.fingerprint,
            active_version=self.baseline.version,
            active_fingerprint=self.baseline.fingerprint,
            evaluation_id=evaluation_2,
            baseline_benchmark_fingerprint="d" * 64,
            candidate_benchmark_fingerprint="e" * 64,
            reproduction_benchmark_fingerprint="d" * 64,
            reproduction_tolerance=0.0,
            created_at="2026-08-29T14:26:00Z",
        )
        self.assertLess(activation_1, activation_2)
        activations = self.repo.activations(candidate.candidate_id)
        self.assertEqual([activation_1, activation_2], [row["id"] for row in activations])
        self.assertEqual(["promote", "rollback"], [row["action"] for row in activations])

    def test_active_context_policy_pointer_is_explicit_and_nullable(self):
        self.assertIsNone(self.repo.active_context_policy_version())
        self.repo.set_active_context_policy_version(
            self.baseline.version,
            updated_at="2026-08-29T14:27:00Z",
        )
        self.assertEqual(self.baseline.version, self.repo.active_context_policy_version())
        self.repo.set_active_context_policy_version(
            None,
            updated_at="2026-08-29T14:28:00Z",
        )
        self.assertIsNone(self.repo.active_context_policy_version())


class LearningPlaneSchemaMigrationTests(unittest.TestCase):
    def test_schema_v22_workspace_is_backed_up_and_upgraded_without_row_loss(self):
        self.assertEqual(23, SCHEMA_VERSION)
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "v22.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                PRAGMA user_version=22;
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '22');
                CREATE TABLE legacy_marker(id TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO legacy_marker VALUES('keep-me', 'preserved');
                """
            )
            conn.close()

            store = Store(db_path)
            try:
                self.assertEqual("preserved", store.conn.execute(
                    "SELECT value FROM legacy_marker WHERE id='keep-me'"
                ).fetchone()[0])
                tables = {
                    row[0]
                    for row in store.conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertTrue(LEARNING_TABLES <= tables)
                self.assertEqual("23", store.get_meta("schema_version"))
                self.assertEqual(23, store.conn.execute("PRAGMA user_version").fetchone()[0])
            finally:
                store.close()

            backup = db_path.with_name("v22.sqlite3.pre-migration-v22")
            self.assertTrue(backup.is_file())
            backup_conn = sqlite3.connect(backup)
            try:
                self.assertEqual(22, backup_conn.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual(
                    "preserved",
                    backup_conn.execute(
                        "SELECT value FROM legacy_marker WHERE id='keep-me'"
                    ).fetchone()[0],
                )
                backup_tables = {
                    row[0]
                    for row in backup_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertTrue(LEARNING_TABLES.isdisjoint(backup_tables))
            finally:
                backup_conn.close()

    def test_future_schema_remains_fail_closed_before_learning_tables_are_created(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "future.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                PRAGMA user_version=24;
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '24');
                CREATE TABLE marker(value TEXT NOT NULL);
                INSERT INTO marker VALUES('untouched');
                """
            )
            conn.close()

            with self.assertRaisesRegex(RuntimeError, "newer"):
                Store(db_path)

            conn = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertEqual({"meta", "marker"}, tables)
                self.assertEqual("untouched", conn.execute("SELECT value FROM marker").fetchone()[0])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

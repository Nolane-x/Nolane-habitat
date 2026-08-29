from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from habitat.learning_plane import ContextPolicy, OutcomeRecord, PolicyCandidate
from habitat.storage import Store


def policy(version: str, graph_depth: int) -> ContextPolicy:
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


class LearningPlaneJsonShapeTests(unittest.TestCase):
    def test_outcome_round_trip_preserves_empty_array_and_empty_object_shapes(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / "habitat.sqlite3")
            try:
                repo = store._learning_repository()
                baseline = policy("context-v1", 2)
                candidate_policy = policy("context-v2", 3)
                repo.create_policy_version(
                    baseline,
                    parent_version=None,
                    created_by="bootstrap",
                    created_at="2026-08-29T15:00:00Z",
                )
                repo.create_policy_version(
                    candidate_policy,
                    parent_version=baseline.version,
                    created_by="generator-v1",
                    created_at="2026-08-29T15:01:00Z",
                )
                candidate = PolicyCandidate(
                    candidate_id="cand-json-shapes",
                    policy_version=candidate_policy.version,
                    policy_fingerprint=candidate_policy.fingerprint,
                    baseline_version=baseline.version,
                    baseline_fingerprint=baseline.fingerprint,
                    generator_id="generator-v1",
                    state="candidate",
                    created_at="2026-08-29T15:02:00Z",
                    updated_at="2026-08-29T15:02:00Z",
                )
                repo.create_candidate(candidate)

                expected = {
                    "empty_array": [],
                    "empty_object": {},
                    "nested": {
                        "items": [],
                        "metadata": {},
                        "mixed": [{}, []],
                    },
                }
                outcome = OutcomeRecord(
                    policy_version=candidate_policy.version,
                    task_fingerprint="task:json-shapes",
                    benchmark_class="semantic navigation",
                    provider_fingerprints=("provider:a",),
                    context_refs=("context:json-shapes",),
                    action_refs=("action:json-shapes",),
                    verification_refs=("verify:json-shapes",),
                    independent_outcome=expected,
                    resource_metrics={},
                    errors=(),
                    rollbacks=(),
                    revision="revision:json-shapes",
                    created_at="2026-08-29T15:03:00Z",
                )
                row_id = repo.append_outcome(candidate.candidate_id, outcome)
                row = store.conn.execute(
                    "SELECT independent_outcome_json FROM learning_outcomes WHERE id=?",
                    (row_id,),
                ).fetchone()

                self.assertEqual(expected, json.loads(row["independent_outcome_json"]))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()

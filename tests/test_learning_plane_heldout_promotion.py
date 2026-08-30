from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.context import ContextCompiler
from habitat.learning_plane import (
    CONSTITUTIONAL_LEARNING_TARGETS,
    ContextPolicy,
    EvaluationPacket,
)
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


SOURCE_TEXT = "def target():\n    return helper()\n\ndef helper():\n    return 1\n"


def digest_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def make_policy(
    version: str,
    *,
    lexical_weight: float,
    parent_budget: int = 1,
) -> ContextPolicy:
    return ContextPolicy(
        version=version,
        lexical_weight=lexical_weight,
        structural_weight=1.0,
        evidence_weight=1.0,
        graph_depth=0,
        max_roots=1,
        source_prefetch_budget=parent_budget,
        abstention_threshold=0.25,
    )


def deterministic_candidates(_compiler, _task, _task_class, _agent_id=None):
    return {
        "heldout:correct": {
            "object_id": "heldout:correct",
            "score": 0.40,
            "reason": "held-out exact lexical evidence",
            "lane": "lexical",
            "kind": "symbol",
            "path": "target.py",
            "trust": "exact",
        },
        "heldout:distractor": {
            "object_id": "heldout:distractor",
            "score": 0.50,
            "reason": "held-out structural distractor",
            "lane": "symbol",
            "kind": "symbol",
            "path": "target.py",
            "trust": "semantic",
        },
    }


class LearningPlaneHeldOutPromotionTests(unittest.TestCase):
    def make_workspace(
        self,
        root: Path,
        name: str,
    ) -> tuple[HabitatWorkspace, Path, Path]:
        source = root / f"{name}-source"
        habitat = root / f"{name}-habitat"
        source.mkdir()
        source_path = source / "target.py"
        source_path.write_text(SOURCE_TEXT, encoding="utf-8")
        return HabitatWorkspace.create(source, habitat), habitat, source_path

    def evaluate_policy(
        self,
        root: Path,
        name: str,
        policy: ContextPolicy,
    ) -> dict:
        ws, _habitat, source_path = self.make_workspace(root, name)
        try:
            service = ws._learning()
            service.register_context_policy(
                policy,
                parent_version=None,
                created_by="heldout-fixture",
            )
            ws.store._learning_repository().set_active_context_policy_version(
                policy.version,
                updated_at="2026-08-29T00:00:00+00:00",
            )
            with patch.object(
                ContextCompiler,
                "_primary_candidates",
                new=deterministic_candidates,
            ), patch.object(
                ContextCompiler,
                "_expand_graph",
                new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
            ), patch.object(
                ContextCompiler,
                "_apply_utility_prior",
                new=lambda _self, _candidates, _task, _agent_id=None: 0,
            ):
                context = ContextCompiler(ws).compile("target", budget=1)

            selected_ids = tuple(obj.object_id for obj in context.objects)
            success = selected_ids == ("heldout:correct",)
            source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            benchmark_fingerprint = digest_payload(
                {
                    "suite_id": "heldout-context-policy-closure-v1",
                    "task": "target",
                    "source_digest": source_digest,
                    "policy_version": policy.version,
                    "policy_fingerprint": policy.fingerprint,
                    "selected_ids": selected_ids,
                    "success": success,
                    "evaluator_id": "independent-heldout-evaluator",
                }
            )
            return {
                "success": success,
                "source_digest": source_digest,
                "selected_ids": selected_ids,
                "benchmark_fingerprint": benchmark_fingerprint,
                "evidence_ref": f"heldout:{benchmark_fingerprint}",
            }
        finally:
            ws.close()

    def advance_to_canary(
        self,
        service,
        candidate_id: str,
        evaluation: EvaluationPacket,
    ) -> None:
        self.assertEqual(
            "shadow",
            service.transition_candidate(candidate_id, "shadow")["state"],
        )
        self.assertEqual(
            "experiment",
            service.transition_candidate(candidate_id, "experiment")["state"],
        )
        admitted = service.admit_evaluation(candidate_id, evaluation)
        self.assertGreater(admitted["evaluation_id"], 0)
        self.assertEqual(
            "evaluated",
            service.transition_candidate(candidate_id, "evaluated")["state"],
        )
        self.assertEqual(
            "canary",
            service.transition_candidate(candidate_id, "canary")["state"],
        )

    def compile_live(self, ws: HabitatWorkspace):
        with patch.object(
            ContextCompiler,
            "_primary_candidates",
            new=deterministic_candidates,
        ), patch.object(
            ContextCompiler,
            "_expand_graph",
            new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
        ), patch.object(
            ContextCompiler,
            "_apply_utility_prior",
            new=lambda _self, _candidates, _task, _agent_id=None: 0,
        ):
            return ContextCompiler(ws).compile("target", budget=1)

    def test_candidate_lineage_must_exactly_bind_the_declared_baseline(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            ws, _habitat, _source = self.make_workspace(root, "lineage")
            try:
                service = ws._learning()
                baseline = make_policy("lineage-baseline-v1", lexical_weight=0.5)
                unrelated = make_policy("lineage-unrelated-v1", lexical_weight=2.0)
                service.register_context_policy(
                    baseline,
                    parent_version=None,
                    created_by="seed",
                )
                service.register_context_policy(
                    unrelated,
                    parent_version=None,
                    created_by="unrelated-generator",
                )
                ws.store._learning_repository().set_active_context_policy_version(
                    baseline.version,
                    updated_at="2026-08-29T00:00:00+00:00",
                )

                with self.assertRaisesRegex(ValueError, "parent|lineage"):
                    service.create_policy_candidate(
                        unrelated.version,
                        baseline_version=baseline.version,
                        generator_id="policy-generator",
                    )
            finally:
                ws.close()

    def test_independent_heldout_improvement_promotes_and_exact_reproduction_rolls_back(self):
        with WorkspaceTemporaryDirectory() as temp:
            root = Path(temp)
            baseline = make_policy("closure-baseline-v1", lexical_weight=0.5)
            candidate = make_policy("closure-candidate-v1", lexical_weight=2.0)

            baseline_result = self.evaluate_policy(root, "baseline-eval", baseline)
            candidate_result = self.evaluate_policy(root, "candidate-eval", candidate)
            self.assertEqual(
                baseline_result["source_digest"],
                candidate_result["source_digest"],
            )
            self.assertFalse(baseline_result["success"])
            self.assertTrue(candidate_result["success"])
            self.assertNotEqual(
                baseline_result["benchmark_fingerprint"],
                candidate_result["benchmark_fingerprint"],
            )

            ws, habitat, _source = self.make_workspace(root, "lifecycle")
            try:
                service = ws._learning()
                service.register_context_policy(
                    baseline,
                    parent_version=None,
                    created_by="seed",
                )
                service.register_context_policy(
                    candidate,
                    parent_version=baseline.version,
                    created_by="policy-generator",
                )
                repository = ws.store._learning_repository()
                repository.set_active_context_policy_version(
                    baseline.version,
                    updated_at="2026-08-29T00:00:00+00:00",
                )
                authorization_before = (habitat / "policy.json").read_bytes()

                created = service.create_policy_candidate(
                    candidate.version,
                    baseline_version=baseline.version,
                    generator_id="policy-generator",
                )
                candidate_id = created["candidate_id"]
                evaluation = EvaluationPacket(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    evaluator_id="independent-heldout-evaluator",
                    heldout_suite_id="heldout-context-policy-closure-v1",
                    baseline_benchmark_fingerprint=baseline_result[
                        "benchmark_fingerprint"
                    ],
                    candidate_benchmark_fingerprint=candidate_result[
                        "benchmark_fingerprint"
                    ],
                    improved=True,
                    evidence_refs=(
                        baseline_result["evidence_ref"],
                        candidate_result["evidence_ref"],
                    ),
                    reproduction_tolerance=0.0,
                )
                self.advance_to_canary(service, candidate_id, evaluation)
                promoted = service.promote_candidate(candidate_id)
                self.assertEqual("promoted", promoted["state"])
                self.assertEqual(candidate.version, promoted["active_version"])

                live_candidate = self.compile_live(ws)
                self.assertEqual(
                    ("heldout:correct",),
                    tuple(obj.object_id for obj in live_candidate.objects),
                )
                self.assertEqual(
                    candidate.version,
                    live_candidate.decision_packet["learning_policy_version"],
                )
                self.assertEqual(
                    candidate.fingerprint,
                    live_candidate.decision_packet["learning_policy_fingerprint"],
                )
                self.assertEqual(
                    authorization_before,
                    (habitat / "policy.json").read_bytes(),
                )

                reproduction = self.evaluate_policy(root, "baseline-reproduction", baseline)
                self.assertEqual(
                    baseline_result["benchmark_fingerprint"],
                    reproduction["benchmark_fingerprint"],
                )

                tampered = EvaluationPacket(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                    evaluator_id="independent-heldout-evaluator",
                    heldout_suite_id="heldout-context-policy-closure-v1",
                    baseline_benchmark_fingerprint=baseline_result[
                        "benchmark_fingerprint"
                    ],
                    candidate_benchmark_fingerprint=digest_payload({"tampered": True}),
                    improved=False,
                    evidence_refs=("heldout:tampered",),
                    reproduction_tolerance=0.0,
                )
                with self.assertRaisesRegex(ValueError, "benchmark fingerprint"):
                    service.rollback_candidate(candidate_id, tampered)

                too_loose = EvaluationPacket(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                    evaluator_id="independent-heldout-evaluator",
                    heldout_suite_id="heldout-context-policy-closure-v1",
                    baseline_benchmark_fingerprint=baseline_result[
                        "benchmark_fingerprint"
                    ],
                    candidate_benchmark_fingerprint=baseline_result[
                        "benchmark_fingerprint"
                    ],
                    improved=False,
                    evidence_refs=(reproduction["evidence_ref"],),
                    reproduction_tolerance=0.01,
                )
                with self.assertRaisesRegex(ValueError, "tolerance"):
                    service.rollback_candidate(candidate_id, too_loose)

                rollback_packet = EvaluationPacket(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                    evaluator_id="independent-heldout-evaluator",
                    heldout_suite_id="heldout-context-policy-closure-v1",
                    baseline_benchmark_fingerprint=baseline_result[
                        "benchmark_fingerprint"
                    ],
                    candidate_benchmark_fingerprint=reproduction[
                        "benchmark_fingerprint"
                    ],
                    improved=False,
                    evidence_refs=(reproduction["evidence_ref"],),
                    reproduction_tolerance=0.0,
                )
                rolled_back = service.rollback_candidate(candidate_id, rollback_packet)
                self.assertEqual("rolled_back", rolled_back["state"])
                self.assertEqual(baseline.version, rolled_back["active_version"])

                live_baseline = self.compile_live(ws)
                self.assertEqual(
                    ("heldout:distractor",),
                    tuple(obj.object_id for obj in live_baseline.objects),
                )
                self.assertEqual(
                    baseline.version,
                    live_baseline.decision_packet["learning_policy_version"],
                )
                self.assertEqual(
                    baseline.fingerprint,
                    live_baseline.decision_packet["learning_policy_fingerprint"],
                )
                self.assertEqual(
                    authorization_before,
                    (habitat / "policy.json").read_bytes(),
                )
            finally:
                ws.close()

    def test_constitutional_targets_remain_unrepresentable_as_context_policy_fields(self):
        baseline_mapping = {
            "version": "constitutional-audit-v1",
            "lexical_weight": 1.0,
            "structural_weight": 1.0,
            "evidence_weight": 1.0,
            "graph_depth": 2,
            "max_roots": 8,
            "source_prefetch_budget": 12,
            "abstention_threshold": 0.25,
        }
        for forbidden in sorted(CONSTITUTIONAL_LEARNING_TARGETS):
            with self.subTest(forbidden=forbidden), self.assertRaisesRegex(
                ValueError,
                "constitutional",
            ):
                ContextPolicy.from_mapping(
                    {
                        **baseline_mapping,
                        forbidden: "attempted-learning-override",
                    }
                )


if __name__ == "__main__":
    unittest.main()

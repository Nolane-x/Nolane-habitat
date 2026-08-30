from __future__ import annotations

from dataclasses import FrozenInstanceError
import math
import re
import unittest

from habitat.learning_plane import (
    CONSTITUTIONAL_LEARNING_TARGETS,
    LEGAL_CANDIDATE_TRANSITIONS,
    ContextPolicy,
    EvaluationPacket,
    OutcomeRecord,
    PolicyCandidate,
)


EXPECTED_CONSTITUTIONAL_TARGETS = frozenset(
    {
        "source_authority_precedence",
        "path_escape_checks",
        "revision_freshness_requirements",
        "mutation_journaling_recovery_rules",
        "approval_requirements",
        "containment_truthfulness_rules",
        "secret_redaction_boundaries",
        "stable_release_review_requirements",
        "authority_class_ordering",
    }
)

EXPECTED_TRANSITIONS = {
    "candidate": frozenset({"shadow", "rejected"}),
    "shadow": frozenset({"experiment", "rejected"}),
    "experiment": frozenset({"evaluated", "rejected"}),
    "evaluated": frozenset({"canary", "rejected"}),
    "canary": frozenset({"promoted", "rejected"}),
    "promoted": frozenset({"rolled_back"}),
    "rejected": frozenset(),
    "rolled_back": frozenset(),
}


def make_policy(**overrides) -> ContextPolicy:
    values = {
        "version": "context-v1",
        "lexical_weight": 1.0,
        "structural_weight": 1.0,
        "evidence_weight": 1.0,
        "graph_depth": 2,
        "max_roots": 8,
        "source_prefetch_budget": 18,
        "abstention_threshold": 0.28,
    }
    values.update(overrides)
    return ContextPolicy(**values)


class ContextPolicyTests(unittest.TestCase):
    def test_policy_is_frozen_and_has_stable_sha256_fingerprint(self):
        policy = make_policy()
        same = make_policy()
        changed = make_policy(graph_depth=3)

        self.assertEqual(policy.fingerprint, same.fingerprint)
        self.assertNotEqual(policy.fingerprint, changed.fingerprint)
        self.assertRegex(policy.fingerprint, re.compile(r"^[0-9a-f]{64}$"))
        with self.assertRaises(FrozenInstanceError):
            policy.graph_depth = 4

    def test_policy_validates_identity_ranges_and_bool_aliases(self):
        with self.assertRaises(ValueError):
            make_policy(version="   ")

        for field in ("lexical_weight", "structural_weight", "evidence_weight"):
            for value in (-0.01, math.inf, math.nan, True):
                with self.subTest(field=field, value=value), self.assertRaises((TypeError, ValueError)):
                    make_policy(**{field: value})

        invalid_ints = {
            "graph_depth": (-1, 9, True),
            "max_roots": (0, 65, True),
            "source_prefetch_budget": (0, 201, True),
        }
        for field, values in invalid_ints.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises((TypeError, ValueError)):
                    make_policy(**{field: value})

        for value in (-0.01, 1.01, math.inf, math.nan, True):
            with self.subTest(abstention=value), self.assertRaises((TypeError, ValueError)):
                make_policy(abstention_threshold=value)

    def test_policy_from_mapping_is_fail_closed_for_unknown_and_constitutional_fields(self):
        base = {
            "version": "context-v1",
            "lexical_weight": 1.0,
            "structural_weight": 1.0,
            "evidence_weight": 1.0,
            "graph_depth": 2,
            "max_roots": 8,
            "source_prefetch_budget": 18,
            "abstention_threshold": 0.28,
        }
        self.assertEqual(make_policy(), ContextPolicy.from_mapping(base))
        with self.assertRaisesRegex(ValueError, "unknown learning policy field"):
            ContextPolicy.from_mapping({**base, "magic_optimizer": 1})
        for field in EXPECTED_CONSTITUTIONAL_TARGETS:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "constitutional"):
                ContextPolicy.from_mapping({**base, field: True})


class ConstitutionalBoundaryTests(unittest.TestCase):
    def test_constitutional_target_set_matches_foundation_convergence_exactly(self):
        self.assertEqual(EXPECTED_CONSTITUTIONAL_TARGETS, CONSTITUTIONAL_LEARNING_TARGETS)


class CandidateLifecycleModelTests(unittest.TestCase):
    def test_transition_graph_matches_foundation_convergence_lifecycle(self):
        self.assertEqual(EXPECTED_TRANSITIONS, LEGAL_CANDIDATE_TRANSITIONS)

    def test_candidate_is_frozen_and_binds_exact_policy_and_generator_identity(self):
        values = {
            "candidate_id": "cand-001",
            "policy_version": "context-v2",
            "policy_fingerprint": "a" * 64,
            "baseline_version": "context-v1",
            "baseline_fingerprint": "b" * 64,
            "generator_id": "candidate-generator-v1",
            "state": "candidate",
            "created_at": "2026-08-29T14:10:00Z",
            "updated_at": "2026-08-29T14:10:00Z",
        }
        candidate = PolicyCandidate(**values)
        self.assertEqual("candidate", candidate.state)
        with self.assertRaises(FrozenInstanceError):
            candidate.state = "shadow"

        for field in (
            "candidate_id",
            "policy_version",
            "policy_fingerprint",
            "baseline_version",
            "baseline_fingerprint",
            "generator_id",
            "created_at",
            "updated_at",
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                PolicyCandidate(**{**values, field: "   "})

        with self.assertRaises(ValueError):
            PolicyCandidate(**{**values, "state": "unknown"})


class EvaluationPacketTests(unittest.TestCase):
    def test_evaluation_packet_is_frozen_and_requires_independent_evaluator(self):
        packet = EvaluationPacket(
            candidate_id="cand-001",
            policy_fingerprint="a" * 64,
            evaluator_id="heldout-evaluator-v1",
            heldout_suite_id="foundation-heldout-v1",
            baseline_benchmark_fingerprint="b" * 64,
            candidate_benchmark_fingerprint="c" * 64,
            improved=True,
            evidence_refs=("benchmark:result:1", "evaluator:receipt:1"),
            reproduction_tolerance=0.0,
        )
        self.assertIs(packet, packet.require_independent("candidate-generator-v1"))
        with self.assertRaisesRegex(ValueError, "independent"):
            packet.require_independent("heldout-evaluator-v1")
        with self.assertRaises(FrozenInstanceError):
            packet.improved = False

    def test_evaluation_packet_validates_types_missingness_and_tolerance(self):
        base = dict(
            candidate_id="cand-001",
            policy_fingerprint="a" * 64,
            evaluator_id="eval-v1",
            heldout_suite_id="heldout-v1",
            baseline_benchmark_fingerprint="b" * 64,
            candidate_benchmark_fingerprint="c" * 64,
            improved=True,
            evidence_refs=("evidence:1",),
            reproduction_tolerance=None,
        )
        packet = EvaluationPacket(**base)
        self.assertIsNone(packet.reproduction_tolerance)

        with self.assertRaises(TypeError):
            EvaluationPacket(**{**base, "improved": 1})
        for value in (-0.01, math.inf, math.nan, True):
            with self.subTest(tolerance=value), self.assertRaises((TypeError, ValueError)):
                EvaluationPacket(**{**base, "reproduction_tolerance": value})
        with self.assertRaises(ValueError):
            EvaluationPacket(**{**base, "evidence_refs": ("",)})


class OutcomeRecordTests(unittest.TestCase):
    def test_outcome_record_normalizes_collections_without_coercing_missing_metrics(self):
        outcome = OutcomeRecord(
            policy_version="context-v2",
            task_fingerprint="task:abc",
            benchmark_class="semantic navigation",
            provider_fingerprints=("provider:b", "provider:a"),
            context_refs=("ctx:2", "ctx:1"),
            action_refs=("action:1",),
            verification_refs=("verify:1",),
            independent_outcome={"success": True, "score": 0.75},
            resource_metrics={"tool_calls": 0, "provider_calls": None},
            errors=(),
            rollbacks=("rollback:0",),
            revision="rev-123",
            created_at="2026-08-29T14:11:00Z",
        )
        self.assertEqual(("provider:a", "provider:b"), outcome.provider_fingerprints)
        self.assertEqual(("ctx:1", "ctx:2"), outcome.context_refs)
        self.assertEqual(0, dict(outcome.resource_metrics)["tool_calls"])
        self.assertIsNone(dict(outcome.resource_metrics)["provider_calls"])
        with self.assertRaises(FrozenInstanceError):
            outcome.revision = "other"

    def test_outcome_record_rejects_invalid_required_identity_and_metrics(self):
        values = dict(
            policy_version="context-v2",
            task_fingerprint="task:abc",
            benchmark_class="semantic navigation",
            provider_fingerprints=(),
            context_refs=(),
            action_refs=(),
            verification_refs=(),
            independent_outcome={"success": False},
            resource_metrics={},
            errors=(),
            rollbacks=(),
            revision="rev-123",
            created_at="2026-08-29T14:11:00Z",
        )
        for field in ("policy_version", "task_fingerprint", "benchmark_class", "revision", "created_at"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                OutcomeRecord(**{**values, field: "   "})
        with self.assertRaises(ValueError):
            OutcomeRecord(**{**values, "resource_metrics": {"wall_ms": -1}})
        with self.assertRaises(TypeError):
            OutcomeRecord(**{**values, "resource_metrics": {"tool_calls": True}})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import FrozenInstanceError
import re
import unittest

from habitat.benchmarking import (
    ABLATION_TARGETS,
    BENCHMARK_CLASSES,
    AblationConfig,
    BenchmarkSpec,
)


EXPECTED_BENCHMARK_CLASSES = (
    "retrieval/orientation",
    "semantic navigation",
    "refactor/rename",
    "debugging",
    "multi-file implementation",
    "test selection",
    "runtime diagnosis",
    "UI tasks",
    "multi-agent invalidation",
    "adversarial/authority tests",
    "large repository scaling",
)

EXPECTED_ABLATION_TARGETS = frozenset(
    {
        "graph_expansion",
        "residency_prior",
        "memory",
        "runtime_evidence",
        "executive_strategy_switching",
    }
)


class BenchmarkLabTaxonomyTests(unittest.TestCase):
    def test_benchmark_class_taxonomy_matches_foundation_convergence_exactly(self):
        self.assertEqual(EXPECTED_BENCHMARK_CLASSES, BENCHMARK_CLASSES)
        self.assertEqual(len(EXPECTED_BENCHMARK_CLASSES), len(set(BENCHMARK_CLASSES)))

    def test_ablation_targets_cover_exact_disableable_subsystem_set(self):
        self.assertEqual(EXPECTED_ABLATION_TARGETS, ABLATION_TARGETS)


class BenchmarkSpecTests(unittest.TestCase):
    def _spec(self, **overrides):
        values = {
            "task_id": "semantic-nav-001",
            "benchmark_class": "semantic navigation",
            "repository_revision": "0123456789abcdef",
            "task_fingerprint": "task-sha256:abc123",
        }
        values.update(overrides)
        return BenchmarkSpec(**values)

    def test_spec_is_frozen(self):
        spec = self._spec()
        with self.assertRaises(FrozenInstanceError):
            spec.task_id = "other"

    def test_spec_rejects_empty_identity_fields(self):
        for field in ("task_id", "repository_revision", "task_fingerprint"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self._spec(**{field: "   "})

    def test_spec_rejects_unknown_benchmark_class(self):
        with self.assertRaisesRegex(ValueError, "unknown benchmark class"):
            self._spec(benchmark_class="generic")

    def test_spec_fingerprint_is_stable_and_materially_sensitive(self):
        first = self._spec()
        same = self._spec()
        changed = self._spec(repository_revision="fedcba9876543210")

        self.assertEqual(first.fingerprint, same.fingerprint)
        self.assertNotEqual(first.fingerprint, changed.fingerprint)
        self.assertRegex(first.fingerprint, re.compile(r"^[0-9a-f]{64}$"))


class AblationConfigTests(unittest.TestCase):
    def test_ablation_config_is_frozen_and_normalizes_subsystems(self):
        config = AblationConfig(disabled_subsystems={"memory", "graph_expansion"})

        self.assertEqual(frozenset({"memory", "graph_expansion"}), config.disabled_subsystems)
        with self.assertRaises(FrozenInstanceError):
            config.semantic_mode = "parser_only"

    def test_ablation_config_rejects_unknown_subsystem(self):
        with self.assertRaisesRegex(ValueError, "unknown ablation target"):
            AblationConfig(disabled_subsystems={"magic_reasoner"})

    def test_ablation_config_uses_single_semantic_mode(self):
        self.assertEqual("default", AblationConfig().semantic_mode)
        self.assertEqual("parser_only", AblationConfig(semantic_mode="parser_only").semantic_mode)
        self.assertEqual(
            "precise_provider",
            AblationConfig(semantic_mode="precise_provider").semantic_mode,
        )
        with self.assertRaisesRegex(ValueError, "unknown semantic mode"):
            AblationConfig(semantic_mode="parser_and_precise")

    def test_ablation_config_uses_single_retrieval_policy_mode(self):
        self.assertEqual("default", AblationConfig().retrieval_policy)
        self.assertEqual("static", AblationConfig(retrieval_policy="static").retrieval_policy)
        self.assertEqual(
            "learned_candidate",
            AblationConfig(retrieval_policy="learned_candidate").retrieval_policy,
        )
        with self.assertRaisesRegex(ValueError, "unknown retrieval policy"):
            AblationConfig(retrieval_policy="static_plus_learned")

    def test_ablation_fingerprint_is_order_independent_and_sensitive(self):
        first = AblationConfig(disabled_subsystems={"memory", "graph_expansion"})
        same = AblationConfig(disabled_subsystems={"graph_expansion", "memory"})
        changed = AblationConfig(
            disabled_subsystems={"memory", "graph_expansion"},
            semantic_mode="parser_only",
        )

        self.assertEqual(first.fingerprint, same.fingerprint)
        self.assertNotEqual(first.fingerprint, changed.fingerprint)
        self.assertRegex(first.fingerprint, re.compile(r"^[0-9a-f]{64}$"))


if __name__ == "__main__":
    unittest.main()

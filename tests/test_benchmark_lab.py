from __future__ import annotations

from dataclasses import FrozenInstanceError
import re
import unittest

from habitat.benchmarking import (
    ABLATION_TARGETS,
    BENCHMARK_CLASSES,
    AblationConfig,
    BenchmarkMetrics,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkSpec,
    EvaluationResult,
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


def make_spec(**overrides):
    values = {
        "task_id": "semantic-nav-001",
        "benchmark_class": "semantic navigation",
        "repository_revision": "0123456789abcdef",
        "task_fingerprint": "task-sha256:abc123",
    }
    values.update(overrides)
    return BenchmarkSpec(**values)


class BenchmarkLabTaxonomyTests(unittest.TestCase):
    def test_benchmark_class_taxonomy_matches_foundation_convergence_exactly(self):
        self.assertEqual(EXPECTED_BENCHMARK_CLASSES, BENCHMARK_CLASSES)
        self.assertEqual(len(EXPECTED_BENCHMARK_CLASSES), len(set(BENCHMARK_CLASSES)))

    def test_ablation_targets_cover_exact_disableable_subsystem_set(self):
        self.assertEqual(EXPECTED_ABLATION_TARGETS, ABLATION_TARGETS)


class BenchmarkSpecTests(unittest.TestCase):
    def test_spec_is_frozen(self):
        spec = make_spec()
        with self.assertRaises(FrozenInstanceError):
            spec.task_id = "other"

    def test_spec_rejects_empty_identity_fields(self):
        for field in ("task_id", "repository_revision", "task_fingerprint"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                make_spec(**{field: "   "})

    def test_spec_rejects_unknown_benchmark_class(self):
        with self.assertRaisesRegex(ValueError, "unknown benchmark class"):
            make_spec(benchmark_class="generic")

    def test_spec_fingerprint_is_stable_and_materially_sensitive(self):
        first = make_spec()
        same = make_spec()
        changed = make_spec(repository_revision="fedcba9876543210")

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


class BenchmarkMetricsTests(unittest.TestCase):
    def test_unavailable_measurements_remain_none_instead_of_becoming_zero(self):
        metrics = BenchmarkMetrics(
            input_tokens=None,
            output_tokens=None,
            context_precision_proxy=None,
            context_recall_proxy=None,
        )

        self.assertIsNone(metrics.input_tokens)
        self.assertIsNone(metrics.output_tokens)
        self.assertIsNone(metrics.context_precision_proxy)
        self.assertIsNone(metrics.context_recall_proxy)

    def test_all_count_and_byte_metrics_reject_negative_values(self):
        fields = (
            "input_tokens",
            "output_tokens",
            "tool_calls",
            "exact_source_bytes",
            "irrelevant_object_admission",
            "provider_calls",
            "failed_strategy_count",
            "repeated_strategy_count",
            "verification_count",
            "mutation_rollback_count",
            "mutation_conflict_count",
        )
        for field in fields:
            with self.subTest(field=field), self.assertRaises(ValueError):
                BenchmarkMetrics(**{field: -1})

    def test_all_timing_metrics_reject_negative_or_nonfinite_values(self):
        for field in ("wall_ms", "ingest_ms", "warm_reconcile_ms"):
            for value in (-0.1, float("nan"), float("inf")):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    BenchmarkMetrics(**{field: value})

    def test_context_quality_proxies_are_bounded_and_finite(self):
        for field in ("context_precision_proxy", "context_recall_proxy"):
            for value in (-0.01, 1.01, float("nan"), float("inf")):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    BenchmarkMetrics(**{field: value})
        metrics = BenchmarkMetrics(context_precision_proxy=0.0, context_recall_proxy=1.0)
        self.assertEqual(0.0, metrics.context_precision_proxy)
        self.assertEqual(1.0, metrics.context_recall_proxy)

    def test_integer_measurements_reject_boolean_values(self):
        with self.assertRaises(TypeError):
            BenchmarkMetrics(tool_calls=True)


class BenchmarkRunTests(unittest.TestCase):
    def _run(self, **overrides):
        spec = make_spec()
        values = {
            "spec_fingerprint": spec.fingerprint,
            "arm": "habitat",
            "repetition": 0,
            "seed": 7,
            "model_id": "provider/model@revision",
            "scaffold_id": "agent-scaffold-v1",
            "metrics": BenchmarkMetrics(tool_calls=3, wall_ms=12.5),
        }
        values.update(overrides)
        return BenchmarkRun(**values)

    def test_run_is_frozen_and_normalizes_evidence_references(self):
        run = self._run(evidence_refs=["trajectory:1", "receipt:2"])

        self.assertEqual(("trajectory:1", "receipt:2"), run.evidence_refs)
        with self.assertRaises(FrozenInstanceError):
            run.model_id = "other"

    def test_run_rejects_empty_or_invalid_causal_controls(self):
        for field in ("spec_fingerprint", "model_id", "scaffold_id"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self._run(**{field: " "})
        with self.assertRaisesRegex(ValueError, "unknown benchmark arm"):
            self._run(arm="mystery")
        with self.assertRaises(ValueError):
            self._run(repetition=-1)
        with self.assertRaises(ValueError):
            self._run(seed=-1)

    def test_run_identity_is_stable_and_changes_for_every_causal_control(self):
        base = self._run()
        self.assertEqual(base.identity, self._run().identity)
        variants = (
            self._run(spec_fingerprint=make_spec(repository_revision="other").fingerprint),
            self._run(arm="filesystem"),
            self._run(repetition=1),
            self._run(seed=8),
            self._run(model_id="other-model"),
            self._run(scaffold_id="other-scaffold"),
            self._run(ablation=AblationConfig(disabled_subsystems={"memory"})),
        )
        for variant in variants:
            with self.subTest(identity=variant.identity):
                self.assertNotEqual(base.identity, variant.identity)
        self.assertRegex(base.identity, re.compile(r"^[0-9a-f]{64}$"))

    def test_agent_claim_is_recorded_but_not_promoted_to_evaluation(self):
        run = self._run(agent_claimed_success=True)
        self.assertTrue(run.agent_claimed_success)
        self.assertFalse(hasattr(run, "success"))


class EvaluationAndResultTests(unittest.TestCase):
    def test_evaluation_requires_independent_evaluator_identity_and_boolean_verdict(self):
        with self.assertRaises(ValueError):
            EvaluationResult(evaluator_id=" ", success=True)
        with self.assertRaises(TypeError):
            EvaluationResult(evaluator_id="hidden-tests-v1", success=1)

        evaluation = EvaluationResult(
            evaluator_id="hidden-tests-v1",
            success=False,
            regression_free=True,
            hidden_test_success=False,
            evidence_refs=["evaluator:receipt:1"],
        )
        self.assertEqual(("evaluator:receipt:1",), evaluation.evidence_refs)

    def test_result_rejects_run_bound_to_a_different_spec(self):
        spec = make_spec()
        other_spec = make_spec(task_id="other-task")
        run = BenchmarkRun(
            spec_fingerprint=other_spec.fingerprint,
            arm="habitat",
            repetition=0,
            seed=7,
            model_id="model",
            scaffold_id="scaffold",
            metrics=BenchmarkMetrics(),
        )
        evaluation = EvaluationResult(evaluator_id="hidden-tests-v1", success=True)

        with self.assertRaisesRegex(ValueError, "spec fingerprint"):
            BenchmarkResult(spec=spec, run=run, evaluation=evaluation)

    def test_result_keeps_independent_verdict_separate_from_agent_claim(self):
        spec = make_spec()
        run = BenchmarkRun(
            spec_fingerprint=spec.fingerprint,
            arm="habitat",
            repetition=0,
            seed=7,
            model_id="model",
            scaffold_id="scaffold",
            metrics=BenchmarkMetrics(),
            agent_claimed_success=True,
        )
        evaluation = EvaluationResult(evaluator_id="hidden-tests-v1", success=False)
        result = BenchmarkResult(spec=spec, run=run, evaluation=evaluation)

        self.assertTrue(result.run.agent_claimed_success)
        self.assertFalse(result.evaluation.success)


if __name__ == "__main__":
    unittest.main()

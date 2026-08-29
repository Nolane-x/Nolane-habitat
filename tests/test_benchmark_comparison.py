from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from habitat.benchmarking import (
    AblationConfig,
    BenchmarkMetrics,
    ConditionComparison,
    MetricDelta,
    PairedRunComparison,
    admit_experiment_results,
    compare_conditions,
)
from tests.test_benchmark_experiment import make_plan, make_record


METRIC_NAMES = (
    "input_tokens",
    "output_tokens",
    "tool_calls",
    "exact_source_bytes",
    "context_precision_proxy",
    "context_recall_proxy",
    "irrelevant_object_admission",
    "wall_ms",
    "ingest_ms",
    "warm_reconcile_ms",
    "provider_calls",
    "failed_strategy_count",
    "repeated_strategy_count",
    "verification_count",
    "mutation_rollback_count",
    "mutation_conflict_count",
)


def planned(plan, condition_id: str, repetition: int):
    return next(
        run
        for run in plan.planned_runs()
        if run.condition_id == condition_id and run.repetition == repetition
    )


class ConditionComparisonTests(unittest.TestCase):
    def test_comparison_pairs_same_repetition_and_seed_in_plan_order(self):
        plan = make_plan(habitat_ablations=())
        records = []
        for repetition in range(3):
            filesystem = planned(plan, "filesystem", repetition)
            habitat = planned(plan, "habitat", repetition)
            records.extend(
                (
                    make_record(
                        plan,
                        habitat,
                        evaluator_success=repetition != 1,
                        metrics=BenchmarkMetrics(input_tokens=20 + repetition),
                    ),
                    make_record(
                        plan,
                        filesystem,
                        evaluator_success=False,
                        metrics=BenchmarkMetrics(input_tokens=10 + repetition),
                    ),
                )
            )

        evidence = admit_experiment_results(plan, tuple(reversed(records)))
        comparison = compare_conditions(evidence, "filesystem", "habitat")

        self.assertIsInstance(comparison, ConditionComparison)
        self.assertEqual("filesystem", comparison.baseline_condition_id)
        self.assertEqual("habitat", comparison.candidate_condition_id)
        self.assertEqual(3, comparison.repetitions_compared)
        self.assertEqual((0, 1, 2), tuple(pair.repetition for pair in comparison.pairs))
        self.assertEqual(plan.seeds, tuple(pair.seed for pair in comparison.pairs))
        self.assertEqual((1, 0, 1), tuple(pair.success_delta for pair in comparison.pairs))

        for pair in comparison.pairs:
            with self.subTest(repetition=pair.repetition):
                self.assertIsInstance(pair, PairedRunComparison)
                self.assertEqual(
                    planned(plan, "filesystem", pair.repetition).identity,
                    pair.baseline_run_identity,
                )
                self.assertEqual(
                    planned(plan, "habitat", pair.repetition).identity,
                    pair.candidate_run_identity,
                )
                self.assertEqual(METRIC_NAMES, tuple(name for name, _delta in pair.metric_deltas))

    def test_partial_evidence_never_cross_pairs_different_seeds(self):
        plan = make_plan(habitat_ablations=())
        fs0 = planned(plan, "filesystem", 0)
        fs1 = planned(plan, "filesystem", 1)
        habitat0 = planned(plan, "habitat", 0)
        habitat2 = planned(plan, "habitat", 2)
        evidence = admit_experiment_results(
            plan,
            (
                make_record(plan, habitat2),
                make_record(plan, fs1),
                make_record(plan, habitat0),
                make_record(plan, fs0),
            ),
        )

        comparison = compare_conditions(evidence, "filesystem", "habitat")
        self.assertEqual(1, comparison.repetitions_compared)
        self.assertEqual((0,), tuple(pair.repetition for pair in comparison.pairs))
        self.assertEqual((plan.seeds[0],), tuple(pair.seed for pair in comparison.pairs))

    def test_metric_deltas_preserve_unavailable_and_explicit_zero(self):
        plan = make_plan(habitat_ablations=())
        filesystem = planned(plan, "filesystem", 0)
        habitat = planned(plan, "habitat", 0)
        evidence = admit_experiment_results(
            plan,
            (
                make_record(
                    plan,
                    filesystem,
                    metrics=BenchmarkMetrics(
                        input_tokens=0,
                        output_tokens=None,
                        tool_calls=0,
                        wall_ms=5.0,
                    ),
                ),
                make_record(
                    plan,
                    habitat,
                    metrics=BenchmarkMetrics(
                        input_tokens=5,
                        output_tokens=0,
                        tool_calls=0,
                        wall_ms=None,
                    ),
                ),
            ),
        )

        pair = compare_conditions(evidence, "filesystem", "habitat").pairs[0]
        metrics = dict(pair.metric_deltas)
        self.assertEqual(MetricDelta(baseline=0, candidate=5, delta=5), metrics["input_tokens"])
        self.assertEqual(
            MetricDelta(baseline=None, candidate=0, delta=None),
            metrics["output_tokens"],
        )
        self.assertEqual(MetricDelta(baseline=0, candidate=0, delta=0), metrics["tool_calls"])
        self.assertEqual(
            MetricDelta(baseline=5.0, candidate=None, delta=None),
            metrics["wall_ms"],
        )

    def test_comparison_uses_independent_evaluator_success_only(self):
        plan = make_plan(habitat_ablations=())
        filesystem = planned(plan, "filesystem", 0)
        habitat = planned(plan, "habitat", 0)
        evidence = admit_experiment_results(
            plan,
            (
                make_record(
                    plan,
                    filesystem,
                    evaluator_success=True,
                    agent_claimed_success=False,
                ),
                make_record(
                    plan,
                    habitat,
                    evaluator_success=False,
                    agent_claimed_success=True,
                ),
            ),
        )
        pair = compare_conditions(evidence, "filesystem", "habitat").pairs[0]
        self.assertTrue(pair.baseline_success)
        self.assertFalse(pair.candidate_success)
        self.assertEqual(-1, pair.success_delta)

    def test_explicit_ablation_condition_can_be_compared_to_habitat_on(self):
        memory_off = AblationConfig(disabled_subsystems={"memory"})
        plan = make_plan(habitat_ablations=(memory_off,))
        condition_id = f"habitat:{memory_off.fingerprint}"
        records = []
        for repetition in range(3):
            records.extend(
                (
                    make_record(plan, planned(plan, "habitat", repetition)),
                    make_record(plan, planned(plan, condition_id, repetition)),
                )
            )
        comparison = compare_conditions(
            admit_experiment_results(plan, records),
            "habitat",
            condition_id,
        )
        self.assertEqual(3, comparison.repetitions_compared)
        self.assertEqual(condition_id, comparison.candidate_condition_id)

    def test_unknown_or_identical_conditions_are_rejected(self):
        plan = make_plan(habitat_ablations=())
        evidence = admit_experiment_results(plan, ())
        for baseline, candidate in (
            ("unknown", "habitat"),
            ("filesystem", "unknown"),
            ("habitat", "habitat"),
        ):
            with self.subTest(baseline=baseline, candidate=candidate), self.assertRaises(ValueError):
                compare_conditions(evidence, baseline, candidate)

    def test_comparison_requires_experiment_evidence(self):
        with self.assertRaises(TypeError):
            compare_conditions("not-evidence", "filesystem", "habitat")

    def test_comparison_output_is_frozen_and_deeply_tuple_based(self):
        plan = make_plan(habitat_ablations=())
        filesystem = planned(plan, "filesystem", 0)
        habitat = planned(plan, "habitat", 0)
        comparison = compare_conditions(
            admit_experiment_results(
                plan,
                (make_record(plan, filesystem), make_record(plan, habitat)),
            ),
            "filesystem",
            "habitat",
        )
        self.assertIsInstance(comparison.pairs, tuple)
        self.assertIsInstance(comparison.pairs[0].metric_deltas, tuple)
        with self.assertRaises(FrozenInstanceError):
            comparison.baseline_condition_id = "other"
        with self.assertRaises(FrozenInstanceError):
            comparison.pairs[0].seed = 999


if __name__ == "__main__":
    unittest.main()

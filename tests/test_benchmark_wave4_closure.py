from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.heldout_evaluator import evaluate_fixture
from benchmarks.heldout_fixtures import FOUNDATION_HELDOUT_SUITE_PATH, materialize_fixture
from habitat.benchmarking import (
    ABLATION_TARGETS,
    AblationConfig,
    BenchmarkSpec,
    ExperimentPlan,
)


class Wave4AblationClosureTests(unittest.TestCase):
    def test_every_required_ablation_variant_is_representable_and_scheduled(self):
        ablations = tuple(
            AblationConfig(disabled_subsystems={target})
            for target in sorted(ABLATION_TARGETS)
        ) + (
            AblationConfig(semantic_mode="parser_only"),
            AblationConfig(semantic_mode="precise_provider"),
            AblationConfig(retrieval_policy="static"),
            AblationConfig(retrieval_policy="learned_candidate"),
        )
        plan = ExperimentPlan(
            experiment_id="wave4-closure-all-ablations",
            spec=BenchmarkSpec(
                task_id="wave4-closure",
                benchmark_class="retrieval/orientation",
                repository_revision="revision-wave4-closure",
                task_fingerprint="task-wave4-closure",
            ),
            model_id="model-wave4-closure",
            scaffold_id="scaffold-wave4-closure",
            evaluator_id="evaluator-wave4-closure",
            environment_fingerprint="environment-wave4-closure",
            seeds=(101, 202, 303),
            habitat_ablations=ablations,
        )

        scheduled = tuple(ablation for _condition, _arm, ablation in plan.conditions[2:])
        self.assertEqual(
            {ablation.fingerprint for ablation in ablations},
            {ablation.fingerprint for ablation in scheduled},
        )
        self.assertEqual(len(ablations), len(scheduled))

        expected_condition_ids = {condition_id for condition_id, _arm, _ablation in plan.conditions}
        for repetition, seed in enumerate(plan.seeds):
            repetition_runs = [run for run in plan.planned_runs() if run.repetition == repetition]
            self.assertEqual({seed}, {run.seed for run in repetition_runs})
            self.assertEqual(expected_condition_ids, {run.condition_id for run in repetition_runs})
            self.assertTrue(
                all(run.arm == "habitat" for run in repetition_runs if run.condition_id.startswith("habitat:"))
            )


class Wave4HeldOutFixtureClosureTests(unittest.TestCase):
    def test_every_foundation_fixture_materializes_and_evaluator_fails_closed_before_solution(self):
        catalog = json.loads(FOUNDATION_HELDOUT_SUITE_PATH.read_text(encoding="utf-8"))
        tasks = catalog["tasks"]
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            for index, task in enumerate(tasks):
                with self.subTest(fixture_id=task["fixture_id"]):
                    root = base / f"fixture-{index:02d}"
                    fixture = materialize_fixture(
                        task["fixture_id"],
                        root,
                        f"wave4-closure-nonce-{index:02d}",
                        expected_benchmark_class=task["benchmark_class"],
                    )
                    verdict = evaluate_fixture(root, fixture.evaluator_payload)
                    self.assertIs(verdict["evaluator_payload_valid"], True)
                    self.assertIs(verdict["regression_free"], True)
                    self.assertIs(verdict["hidden_test_success"], False)
                    self.assertIs(verdict["success"], False)


if __name__ == "__main__":
    unittest.main()

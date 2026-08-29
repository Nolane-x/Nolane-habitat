from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import random
import re
import unittest

from habitat.benchmarking import (
    AblationConfig,
    BenchmarkSpec,
    ExperimentPlan,
    PlannedRun,
)


def make_spec(**overrides) -> BenchmarkSpec:
    values = {
        "task_id": "semantic-nav-heldout-001",
        "benchmark_class": "semantic navigation",
        "repository_revision": "0123456789abcdef",
        "task_fingerprint": "task-sha256:heldout-abc123",
    }
    values.update(overrides)
    return BenchmarkSpec(**values)


def make_plan(**overrides) -> ExperimentPlan:
    values = {
        "experiment_id": "wave4b-exp-001",
        "spec": make_spec(),
        "model_id": "provider/model@revision",
        "scaffold_id": "agent-scaffold-v1",
        "evaluator_id": "hidden-evaluator-v1",
        "environment_fingerprint": "env-sha256:deadbeef",
        "seeds": (11, 22, 33),
        "habitat_ablations": (
            AblationConfig(disabled_subsystems={"memory"}),
            AblationConfig(semantic_mode="parser_only"),
        ),
    }
    values.update(overrides)
    return ExperimentPlan(**values)


def expected_condition_order(plan: ExperimentPlan, seed: int) -> tuple[str, ...]:
    material = f"{plan.experiment_id}\0{plan.spec.fingerprint}\0{seed}".encode("utf-8")
    stable_seed = int.from_bytes(sha256(material).digest()[:8], "big")
    rng = random.Random(stable_seed)
    condition_ids = [condition_id for condition_id, _arm, _ablation in plan.conditions]
    rng.shuffle(condition_ids)
    return tuple(condition_ids)


class ExperimentPlanValidationTests(unittest.TestCase):
    def test_plan_is_frozen_and_exposes_repetition_count(self):
        plan = make_plan()
        self.assertEqual(3, plan.repetitions)
        with self.assertRaises(FrozenInstanceError):
            plan.model_id = "other-model"

    def test_plan_requires_at_least_three_repetitions(self):
        with self.assertRaisesRegex(ValueError, "at least 3"):
            make_plan(seeds=(1, 2))

    def test_plan_rejects_negative_boolean_and_duplicate_seeds(self):
        invalid = (
            ((1, -2, 3), ValueError),
            ((1, True, 3), TypeError),
            ((1, 1, 2), ValueError),
        )
        for seeds, error_type in invalid:
            with self.subTest(seeds=seeds), self.assertRaises(error_type):
                make_plan(seeds=seeds)

    def test_plan_rejects_empty_causal_identity_fields(self):
        for field in (
            "experiment_id",
            "model_id",
            "scaffold_id",
            "evaluator_id",
            "environment_fingerprint",
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                make_plan(**{field: "   "})

    def test_plan_requires_a_real_benchmark_spec(self):
        with self.assertRaises(TypeError):
            make_plan(spec="not-a-spec")

    def test_plan_rejects_default_and_duplicate_explicit_ablations(self):
        with self.assertRaisesRegex(ValueError, "default ablation"):
            make_plan(habitat_ablations=(AblationConfig(),))

        memory = AblationConfig(disabled_subsystems={"memory"})
        with self.assertRaisesRegex(ValueError, "duplicate ablation"):
            make_plan(habitat_ablations=(memory, memory))

    def test_plan_rejects_non_ablation_entries(self):
        with self.assertRaises(TypeError):
            make_plan(habitat_ablations=("memory-off",))


class ExperimentConditionTests(unittest.TestCase):
    def test_conditions_always_include_filesystem_and_habitat_on(self):
        plan = make_plan(habitat_ablations=())
        self.assertEqual(
            (
                ("filesystem", "filesystem", AblationConfig()),
                ("habitat", "habitat", AblationConfig()),
            ),
            plan.conditions,
        )

    def test_each_explicit_ablation_is_a_unique_habitat_condition(self):
        plan = make_plan()
        conditions = plan.conditions
        self.assertEqual(4, len(conditions))

        filesystem = conditions[0]
        habitat_on = conditions[1]
        self.assertEqual(("filesystem", "filesystem", AblationConfig()), filesystem)
        self.assertEqual(("habitat", "habitat", AblationConfig()), habitat_on)

        for condition_id, arm, ablation in conditions[2:]:
            with self.subTest(condition_id=condition_id):
                self.assertEqual("habitat", arm)
                self.assertNotEqual(AblationConfig(), ablation)
                self.assertEqual(f"habitat:{ablation.fingerprint}", condition_id)

        self.assertEqual(
            {ablation.fingerprint for ablation in plan.habitat_ablations},
            {ablation.fingerprint for _condition_id, _arm, ablation in conditions[2:]},
        )


class PlannedRunTests(unittest.TestCase):
    def test_planned_runs_cover_every_condition_once_per_repetition(self):
        plan = make_plan()
        runs = plan.planned_runs()
        self.assertEqual(plan.repetitions * len(plan.conditions), len(runs))
        self.assertTrue(all(isinstance(run, PlannedRun) for run in runs))

        expected_conditions = {condition_id for condition_id, _arm, _ablation in plan.conditions}
        for repetition, seed in enumerate(plan.seeds):
            with self.subTest(repetition=repetition, seed=seed):
                repetition_runs = [run for run in runs if run.repetition == repetition]
                self.assertEqual(len(plan.conditions), len(repetition_runs))
                self.assertEqual({seed}, {run.seed for run in repetition_runs})
                self.assertEqual(expected_conditions, {run.condition_id for run in repetition_runs})

    def test_filesystem_never_receives_internal_ablation(self):
        plan = make_plan()
        for run in plan.planned_runs():
            if run.arm == "filesystem":
                self.assertEqual(AblationConfig(), run.ablation)
                self.assertEqual("filesystem", run.condition_id)

    def test_execution_order_uses_stable_sha256_seeded_shuffle(self):
        first = make_plan()
        second = make_plan()
        self.assertEqual(first.planned_runs(), second.planned_runs())

        for repetition, seed in enumerate(first.seeds):
            actual = tuple(
                run.condition_id
                for run in first.planned_runs()
                if run.repetition == repetition
            )
            self.assertEqual(expected_condition_order(first, seed), actual)

    def test_planned_run_identity_is_stable_and_hex_sha256(self):
        plan = make_plan()
        first = plan.planned_runs()[0]
        same = make_plan().planned_runs()[0]
        self.assertEqual(first.identity, same.identity)
        self.assertRegex(first.identity, re.compile(r"^[0-9a-f]{64}$"))

    def test_run_identity_changes_with_every_causal_control(self):
        base_plan = make_plan(habitat_ablations=())
        base = next(run for run in base_plan.planned_runs() if run.condition_id == "habitat" and run.repetition == 0)

        variants = (
            make_plan(experiment_id="other-exp", habitat_ablations=()),
            make_plan(spec=make_spec(task_id="other-task"), habitat_ablations=()),
            make_plan(model_id="other-model", habitat_ablations=()),
            make_plan(scaffold_id="other-scaffold", habitat_ablations=()),
            make_plan(evaluator_id="other-evaluator", habitat_ablations=()),
            make_plan(environment_fingerprint="env:other", habitat_ablations=()),
            make_plan(seeds=(12, 22, 33), habitat_ablations=()),
        )
        for plan in variants:
            variant = next(
                run
                for run in plan.planned_runs()
                if run.condition_id == "habitat" and run.repetition == 0
            )
            with self.subTest(identity=variant.identity):
                self.assertNotEqual(base.identity, variant.identity)

        memory_plan = make_plan(
            habitat_ablations=(AblationConfig(disabled_subsystems={"memory"}),)
        )
        runtime_plan = make_plan(
            habitat_ablations=(AblationConfig(disabled_subsystems={"runtime_evidence"}),)
        )
        memory_run = next(run for run in memory_plan.planned_runs() if run.condition_id.startswith("habitat:"))
        runtime_run = next(run for run in runtime_plan.planned_runs() if run.condition_id.startswith("habitat:"))
        self.assertNotEqual(memory_run.identity, runtime_run.identity)

    def test_planned_run_is_frozen(self):
        run = make_plan().planned_runs()[0]
        with self.assertRaises(FrozenInstanceError):
            run.seed = 999


if __name__ == "__main__":
    unittest.main()

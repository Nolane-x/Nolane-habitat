from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import random
import re
import unittest

from habitat.benchmarking import (
    AblationConfig,
    BenchmarkMetrics,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkSpec,
    EvaluationResult,
    ExperimentEvidence,
    ExperimentPlan,
    PlannedRun,
    RecordedBenchmarkResult,
    admit_experiment_results,
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


def make_record(
    plan: ExperimentPlan,
    planned: PlannedRun,
    *,
    planned_run_identity: str | None = None,
    environment_fingerprint: str | None = None,
    spec: BenchmarkSpec | None = None,
    spec_fingerprint: str | None = None,
    arm: str | None = None,
    repetition: int | None = None,
    seed: int | None = None,
    model_id: str | None = None,
    scaffold_id: str | None = None,
    ablation: AblationConfig | None = None,
    evaluator_id: str | None = None,
    evaluator_success: bool = True,
    agent_claimed_success: bool | None = None,
    metrics: BenchmarkMetrics | None = None,
) -> RecordedBenchmarkResult:
    actual_spec = plan.spec if spec is None else spec
    run = BenchmarkRun(
        spec_fingerprint=(
            actual_spec.fingerprint if spec_fingerprint is None else spec_fingerprint
        ),
        arm=planned.arm if arm is None else arm,
        repetition=planned.repetition if repetition is None else repetition,
        seed=planned.seed if seed is None else seed,
        model_id=planned.model_id if model_id is None else model_id,
        scaffold_id=planned.scaffold_id if scaffold_id is None else scaffold_id,
        metrics=BenchmarkMetrics(input_tokens=0, tool_calls=0, wall_ms=0.0)
        if metrics is None
        else metrics,
        ablation=planned.ablation if ablation is None else ablation,
        agent_claimed_success=agent_claimed_success,
        evidence_refs=("trajectory:raw",),
    )
    result = BenchmarkResult(
        spec=actual_spec,
        run=run,
        evaluation=EvaluationResult(
            evaluator_id=planned.evaluator_id if evaluator_id is None else evaluator_id,
            success=evaluator_success,
            evidence_refs=("evaluator:hidden",),
        ),
    )
    return RecordedBenchmarkResult(
        planned_run_identity=(
            planned.identity if planned_run_identity is None else planned_run_identity
        ),
        environment_fingerprint=(
            planned.environment_fingerprint
            if environment_fingerprint is None
            else environment_fingerprint
        ),
        result=result,
    )


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


class ExperimentEvidenceAdmissionTests(unittest.TestCase):
    def test_recorded_result_is_frozen_and_requires_receipt_identity(self):
        plan = make_plan(habitat_ablations=())
        planned = plan.planned_runs()[0]
        record = make_record(plan, planned)
        with self.assertRaises(FrozenInstanceError):
            record.environment_fingerprint = "other"
        with self.assertRaises(ValueError):
            RecordedBenchmarkResult(
                planned_run_identity="   ",
                environment_fingerprint=planned.environment_fingerprint,
                result=record.result,
            )
        with self.assertRaises(ValueError):
            RecordedBenchmarkResult(
                planned_run_identity=planned.identity,
                environment_fingerprint="   ",
                result=record.result,
            )

    def test_partial_evidence_preserves_exact_missing_planned_identities(self):
        plan = make_plan(habitat_ablations=())
        planned_runs = plan.planned_runs()
        evidence = admit_experiment_results(plan, (make_record(plan, planned_runs[0]),))
        self.assertIsInstance(evidence, ExperimentEvidence)
        self.assertFalse(evidence.complete)
        self.assertEqual((planned_runs[0].identity,), tuple(r.planned_run_identity for r in evidence.records))
        self.assertEqual(
            tuple(run.identity for run in planned_runs[1:]),
            evidence.missing_run_identities,
        )

    def test_complete_evidence_requires_one_independent_result_for_every_planned_run(self):
        plan = make_plan()
        records = tuple(make_record(plan, planned) for planned in plan.planned_runs())
        evidence = admit_experiment_results(plan, records)
        self.assertTrue(evidence.complete)
        self.assertEqual((), evidence.missing_run_identities)
        self.assertEqual(records, evidence.records)

    def test_agent_self_report_does_not_override_independent_evaluator(self):
        plan = make_plan(habitat_ablations=())
        planned = plan.planned_runs()[0]
        record = make_record(
            plan,
            planned,
            evaluator_success=False,
            agent_claimed_success=True,
        )
        evidence = admit_experiment_results(plan, (record,))
        self.assertTrue(evidence.records[0].result.run.agent_claimed_success)
        self.assertFalse(evidence.records[0].result.evaluation.success)

    def test_admission_rejects_receipt_not_bound_to_exact_plan(self):
        plan = make_plan(habitat_ablations=())
        planned = next(run for run in plan.planned_runs() if run.condition_id == "habitat")
        other_spec = make_spec(task_id="other-task")
        cases = {
            "unknown planned identity": make_record(
                plan,
                planned,
                planned_run_identity="0" * 64,
            ),
            "environment": make_record(
                plan,
                planned,
                environment_fingerprint="env-sha256:other",
            ),
            "spec": make_record(plan, planned, spec=other_spec),
            "arm": make_record(plan, planned, arm="filesystem"),
            "repetition": make_record(plan, planned, repetition=planned.repetition + 1),
            "seed": make_record(plan, planned, seed=planned.seed + 1),
            "model": make_record(plan, planned, model_id="other-model"),
            "scaffold": make_record(plan, planned, scaffold_id="other-scaffold"),
            "ablation": make_record(
                plan,
                planned,
                ablation=AblationConfig(disabled_subsystems={"memory"}),
            ),
            "evaluator": make_record(plan, planned, evaluator_id="other-evaluator"),
        }
        for label, record in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                admit_experiment_results(plan, (record,))

    def test_admission_rejects_impossible_filesystem_ablation(self):
        plan = make_plan(habitat_ablations=())
        planned = next(run for run in plan.planned_runs() if run.condition_id == "filesystem")
        record = make_record(
            plan,
            planned,
            ablation=AblationConfig(disabled_subsystems={"memory"}),
        )
        with self.assertRaises(ValueError):
            admit_experiment_results(plan, (record,))

    def test_admission_rejects_duplicate_planned_run_identity(self):
        plan = make_plan(habitat_ablations=())
        planned = plan.planned_runs()[0]
        record = make_record(plan, planned)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            admit_experiment_results(plan, (record, record))

    def test_admission_rejects_non_record_entries(self):
        plan = make_plan(habitat_ablations=())
        with self.assertRaises(TypeError):
            admit_experiment_results(plan, ("not-a-record",))


if __name__ == "__main__":
    unittest.main()
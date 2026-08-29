from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import random

from .model import (
    BENCHMARK_ARMS,
    AblationConfig,
    BenchmarkArm,
    BenchmarkResult,
    BenchmarkSpec,
    _fingerprint,
    _require_non_empty,
    _require_non_negative_int,
)


_DEFAULT_ABLATION = AblationConfig()
_METRIC_NAMES = (
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


def _normalize_seeds(value: object) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError("seeds must be an iterable of integers")
    try:
        seeds = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("seeds must be an iterable of integers") from exc

    for seed in seeds:
        _require_non_negative_int(seed, "seed")
    if len(seeds) < 3:
        raise ValueError("experiment plan requires at least 3 seeds")
    if len(set(seeds)) != len(seeds):
        raise ValueError("experiment plan seeds must be unique")
    return seeds


def _normalize_ablations(value: object) -> tuple[AblationConfig, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError("habitat_ablations must be an iterable of AblationConfig")
    try:
        ablations = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("habitat_ablations must be an iterable of AblationConfig") from exc

    fingerprints: set[str] = set()
    for ablation in ablations:
        if not isinstance(ablation, AblationConfig):
            raise TypeError("habitat_ablations entries must be AblationConfig")
        if ablation == _DEFAULT_ABLATION:
            raise ValueError("default ablation is implicit and must not be listed")
        if ablation.fingerprint in fingerprints:
            raise ValueError("duplicate ablation in habitat_ablations")
        fingerprints.add(ablation.fingerprint)
    return ablations


def _condition_id(arm: BenchmarkArm, ablation: AblationConfig) -> str:
    if arm == "filesystem":
        if ablation != _DEFAULT_ABLATION:
            raise ValueError("filesystem condition cannot carry a Habitat ablation")
        return "filesystem"
    if arm == "habitat":
        if ablation == _DEFAULT_ABLATION:
            return "habitat"
        return f"habitat:{ablation.fingerprint}"
    raise ValueError(f"unknown benchmark arm: {arm}")


@dataclass(frozen=True)
class PlannedRun:
    experiment_id: str
    spec_fingerprint: str
    condition_id: str
    arm: BenchmarkArm
    repetition: int
    seed: int
    model_id: str
    scaffold_id: str
    evaluator_id: str
    environment_fingerprint: str
    ablation: AblationConfig = AblationConfig()

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.spec_fingerprint, "spec_fingerprint")
        _require_non_empty(self.condition_id, "condition_id")
        _require_non_empty(self.model_id, "model_id")
        _require_non_empty(self.scaffold_id, "scaffold_id")
        _require_non_empty(self.evaluator_id, "evaluator_id")
        _require_non_empty(self.environment_fingerprint, "environment_fingerprint")
        if self.arm not in BENCHMARK_ARMS:
            raise ValueError(f"unknown benchmark arm: {self.arm}")
        _require_non_negative_int(self.repetition, "repetition")
        _require_non_negative_int(self.seed, "seed")
        if not isinstance(self.ablation, AblationConfig):
            raise TypeError("ablation must be AblationConfig")

        expected_condition_id = _condition_id(self.arm, self.ablation)
        if self.condition_id != expected_condition_id:
            raise ValueError(
                "condition_id does not match benchmark arm and ablation: "
                f"expected {expected_condition_id}"
            )

    @property
    def identity(self) -> str:
        return _fingerprint(
            {
                "experiment_id": self.experiment_id,
                "spec_fingerprint": self.spec_fingerprint,
                "condition_id": self.condition_id,
                "arm": self.arm,
                "repetition": self.repetition,
                "seed": self.seed,
                "model_id": self.model_id,
                "scaffold_id": self.scaffold_id,
                "evaluator_id": self.evaluator_id,
                "environment_fingerprint": self.environment_fingerprint,
                "ablation_fingerprint": self.ablation.fingerprint,
            }
        )


@dataclass(frozen=True)
class ExperimentPlan:
    experiment_id: str
    spec: BenchmarkSpec
    model_id: str
    scaffold_id: str
    evaluator_id: str
    environment_fingerprint: str
    seeds: tuple[int, ...]
    habitat_ablations: tuple[AblationConfig, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.model_id, "model_id")
        _require_non_empty(self.scaffold_id, "scaffold_id")
        _require_non_empty(self.evaluator_id, "evaluator_id")
        _require_non_empty(self.environment_fingerprint, "environment_fingerprint")
        if not isinstance(self.spec, BenchmarkSpec):
            raise TypeError("spec must be BenchmarkSpec")
        object.__setattr__(self, "seeds", _normalize_seeds(self.seeds))
        object.__setattr__(
            self,
            "habitat_ablations",
            _normalize_ablations(self.habitat_ablations),
        )

    @property
    def repetitions(self) -> int:
        return len(self.seeds)

    @property
    def conditions(self) -> tuple[tuple[str, BenchmarkArm, AblationConfig], ...]:
        base: list[tuple[str, BenchmarkArm, AblationConfig]] = [
            ("filesystem", "filesystem", _DEFAULT_ABLATION),
            ("habitat", "habitat", _DEFAULT_ABLATION),
        ]
        base.extend(
            (f"habitat:{ablation.fingerprint}", "habitat", ablation)
            for ablation in self.habitat_ablations
        )
        return tuple(base)

    def planned_runs(self) -> tuple[PlannedRun, ...]:
        runs: list[PlannedRun] = []
        for repetition, seed in enumerate(self.seeds):
            conditions = list(self.conditions)
            seed_material = (
                f"{self.experiment_id}\0{self.spec.fingerprint}\0{seed}"
            ).encode("utf-8")
            stable_seed = int.from_bytes(sha256(seed_material).digest()[:8], "big")
            random.Random(stable_seed).shuffle(conditions)

            for condition_id, arm, ablation in conditions:
                runs.append(
                    PlannedRun(
                        experiment_id=self.experiment_id,
                        spec_fingerprint=self.spec.fingerprint,
                        condition_id=condition_id,
                        arm=arm,
                        repetition=repetition,
                        seed=seed,
                        model_id=self.model_id,
                        scaffold_id=self.scaffold_id,
                        evaluator_id=self.evaluator_id,
                        environment_fingerprint=self.environment_fingerprint,
                        ablation=ablation,
                    )
                )
        return tuple(runs)


@dataclass(frozen=True)
class RecordedBenchmarkResult:
    """A benchmark result accompanied by the causal receipt omitted from BenchmarkRun."""

    planned_run_identity: str
    environment_fingerprint: str
    result: BenchmarkResult

    def __post_init__(self) -> None:
        _require_non_empty(self.planned_run_identity, "planned_run_identity")
        _require_non_empty(self.environment_fingerprint, "environment_fingerprint")
        if not isinstance(self.result, BenchmarkResult):
            raise TypeError("result must be BenchmarkResult")


def _normalize_records(value: object) -> tuple[RecordedBenchmarkResult, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError("records must be an iterable of RecordedBenchmarkResult")
    try:
        records = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("records must be an iterable of RecordedBenchmarkResult") from exc
    for record in records:
        if not isinstance(record, RecordedBenchmarkResult):
            raise TypeError("records entries must be RecordedBenchmarkResult")
    return records


def _validate_record_against_planned_run(
    record: RecordedBenchmarkResult,
    planned: PlannedRun,
) -> None:
    if record.environment_fingerprint != planned.environment_fingerprint:
        raise ValueError("record environment fingerprint does not match planned run")

    result = record.result
    run = result.run
    evaluation = result.evaluation

    if result.spec.fingerprint != planned.spec_fingerprint:
        raise ValueError("record benchmark spec does not match planned run")
    if run.spec_fingerprint != planned.spec_fingerprint:
        raise ValueError("record run spec fingerprint does not match planned run")
    if run.arm != planned.arm:
        raise ValueError("record benchmark arm does not match planned run")
    if run.repetition != planned.repetition:
        raise ValueError("record repetition does not match planned run")
    if run.seed != planned.seed:
        raise ValueError("record seed does not match planned run")
    if run.model_id != planned.model_id:
        raise ValueError("record model does not match planned run")
    if run.scaffold_id != planned.scaffold_id:
        raise ValueError("record scaffold does not match planned run")
    if run.ablation != planned.ablation:
        raise ValueError("record ablation does not match planned run")
    if evaluation.evaluator_id != planned.evaluator_id:
        raise ValueError("record evaluator does not match planned run")

    actual_condition_id = _condition_id(run.arm, run.ablation)
    if actual_condition_id != planned.condition_id:
        raise ValueError("record condition does not match planned run")


@dataclass(frozen=True)
class ExperimentEvidence:
    plan: ExperimentPlan
    records: tuple[RecordedBenchmarkResult, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.plan, ExperimentPlan):
            raise TypeError("plan must be ExperimentPlan")
        records = _normalize_records(self.records)
        planned_runs = self.plan.planned_runs()
        planned_by_identity = {run.identity: run for run in planned_runs}
        seen: set[str] = set()

        for record in records:
            identity = record.planned_run_identity
            if identity in seen:
                raise ValueError(f"duplicate planned run identity: {identity}")
            planned = planned_by_identity.get(identity)
            if planned is None:
                raise ValueError("record planned run identity is not part of experiment plan")
            _validate_record_against_planned_run(record, planned)
            seen.add(identity)

        object.__setattr__(self, "records", records)

    @property
    def missing_run_identities(self) -> tuple[str, ...]:
        admitted = {record.planned_run_identity for record in self.records}
        return tuple(
            planned.identity
            for planned in self.plan.planned_runs()
            if planned.identity not in admitted
        )

    @property
    def complete(self) -> bool:
        return not self.missing_run_identities


def admit_experiment_results(
    plan: ExperimentPlan,
    records: object,
) -> ExperimentEvidence:
    """Admit only independently evaluated receipts bound to exact planned runs."""

    return ExperimentEvidence(plan=plan, records=_normalize_records(records))


@dataclass(frozen=True)
class MetricDelta:
    baseline: int | float | None
    candidate: int | float | None
    delta: int | float | None


@dataclass(frozen=True)
class PairedRunComparison:
    repetition: int
    seed: int
    baseline_run_identity: str
    candidate_run_identity: str
    baseline_success: bool
    candidate_success: bool
    success_delta: int
    metric_deltas: tuple[tuple[str, MetricDelta], ...]


@dataclass(frozen=True)
class ConditionComparison:
    baseline_condition_id: str
    candidate_condition_id: str
    pairs: tuple[PairedRunComparison, ...]

    @property
    def repetitions_compared(self) -> int:
        return len(self.pairs)


def _metric_delta(baseline: int | float | None, candidate: int | float | None) -> MetricDelta:
    delta: int | float | None
    if baseline is None or candidate is None:
        delta = None
    else:
        delta = candidate - baseline
    return MetricDelta(baseline=baseline, candidate=candidate, delta=delta)


def compare_conditions(
    evidence: ExperimentEvidence,
    baseline_condition_id: str,
    candidate_condition_id: str,
) -> ConditionComparison:
    """Compare causally paired condition results without hiding per-run missingness."""

    if not isinstance(evidence, ExperimentEvidence):
        raise TypeError("evidence must be ExperimentEvidence")

    condition_ids = {condition_id for condition_id, _arm, _ablation in evidence.plan.conditions}
    if baseline_condition_id not in condition_ids:
        raise ValueError(f"unknown baseline condition: {baseline_condition_id}")
    if candidate_condition_id not in condition_ids:
        raise ValueError(f"unknown candidate condition: {candidate_condition_id}")
    if baseline_condition_id == candidate_condition_id:
        raise ValueError("baseline and candidate conditions must differ")

    records_by_identity = {
        record.planned_run_identity: record
        for record in evidence.records
    }
    planned_by_condition_and_repetition = {
        (planned.condition_id, planned.repetition): planned
        for planned in evidence.plan.planned_runs()
    }

    pairs: list[PairedRunComparison] = []
    for repetition, seed in enumerate(evidence.plan.seeds):
        baseline_planned = planned_by_condition_and_repetition[(baseline_condition_id, repetition)]
        candidate_planned = planned_by_condition_and_repetition[(candidate_condition_id, repetition)]
        if baseline_planned.seed != seed or candidate_planned.seed != seed:
            raise ValueError("planned condition seeds do not match experiment repetition")

        baseline_record = records_by_identity.get(baseline_planned.identity)
        candidate_record = records_by_identity.get(candidate_planned.identity)
        if baseline_record is None or candidate_record is None:
            continue

        baseline_result = baseline_record.result
        candidate_result = candidate_record.result
        baseline_success = baseline_result.evaluation.success
        candidate_success = candidate_result.evaluation.success
        metric_deltas = tuple(
            (
                metric_name,
                _metric_delta(
                    getattr(baseline_result.run.metrics, metric_name),
                    getattr(candidate_result.run.metrics, metric_name),
                ),
            )
            for metric_name in _METRIC_NAMES
        )

        pairs.append(
            PairedRunComparison(
                repetition=repetition,
                seed=seed,
                baseline_run_identity=baseline_planned.identity,
                candidate_run_identity=candidate_planned.identity,
                baseline_success=baseline_success,
                candidate_success=candidate_success,
                success_delta=int(candidate_success) - int(baseline_success),
                metric_deltas=metric_deltas,
            )
        )

    return ConditionComparison(
        baseline_condition_id=baseline_condition_id,
        candidate_condition_id=candidate_condition_id,
        pairs=tuple(pairs),
    )

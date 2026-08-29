from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import random

from .model import (
    BENCHMARK_ARMS,
    AblationConfig,
    BenchmarkArm,
    BenchmarkSpec,
    _fingerprint,
    _require_non_empty,
    _require_non_negative_int,
)


_DEFAULT_ABLATION = AblationConfig()


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

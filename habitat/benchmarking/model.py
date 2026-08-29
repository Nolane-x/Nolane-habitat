from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Literal

BenchmarkClass = Literal[
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
]
BenchmarkArm = Literal["filesystem", "habitat"]
SemanticMode = Literal["default", "parser_only", "precise_provider"]
RetrievalPolicy = Literal["default", "static", "learned_candidate"]

BENCHMARK_CLASSES: tuple[BenchmarkClass, ...] = (
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

BENCHMARK_ARMS = frozenset({"filesystem", "habitat"})
ABLATION_TARGETS = frozenset(
    {
        "graph_expansion",
        "residency_prior",
        "memory",
        "runtime_evidence",
        "executive_strategy_switching",
    }
)
SEMANTIC_MODES = frozenset({"default", "parser_only", "precise_provider"})
RETRIEVAL_POLICIES = frozenset({"default", "static", "learned_candidate"})


def _require_non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _require_non_negative_int(value: object, field_name: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        expected = "int or None" if nullable else "int"
        raise TypeError(f"{field_name} must be {expected}")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_non_negative_number(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


def _require_optional_unit_interval(value: object, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number or None")
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{field_name} must be finite and between 0 and 1")


def _require_optional_bool(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool or None")


def _normalize_evidence_refs(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError("evidence_refs must be an iterable of evidence identifiers")
    try:
        refs = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("evidence_refs must be an iterable of evidence identifiers") from exc
    for ref in refs:
        _require_non_empty(ref, "evidence reference")
    return refs


@dataclass(frozen=True)
class BenchmarkSpec:
    task_id: str
    benchmark_class: BenchmarkClass
    repository_revision: str
    task_fingerprint: str

    def __post_init__(self) -> None:
        _require_non_empty(self.task_id, "task_id")
        _require_non_empty(self.repository_revision, "repository_revision")
        _require_non_empty(self.task_fingerprint, "task_fingerprint")
        if self.benchmark_class not in BENCHMARK_CLASSES:
            raise ValueError(f"unknown benchmark class: {self.benchmark_class}")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "task_id": self.task_id,
                "benchmark_class": self.benchmark_class,
                "repository_revision": self.repository_revision,
                "task_fingerprint": self.task_fingerprint,
            }
        )


@dataclass(frozen=True)
class AblationConfig:
    disabled_subsystems: frozenset[str] = frozenset()
    semantic_mode: SemanticMode = "default"
    retrieval_policy: RetrievalPolicy = "default"

    def __post_init__(self) -> None:
        if isinstance(self.disabled_subsystems, str):
            raise TypeError("disabled_subsystems must be an iterable of subsystem names")
        try:
            normalized = frozenset(self.disabled_subsystems)
        except TypeError as exc:
            raise TypeError("disabled_subsystems must be an iterable of subsystem names") from exc
        for target in normalized:
            _require_non_empty(target, "ablation target")
        unknown = normalized - ABLATION_TARGETS
        if unknown:
            raise ValueError(f"unknown ablation target: {sorted(unknown)[0]}")
        if self.semantic_mode not in SEMANTIC_MODES:
            raise ValueError(f"unknown semantic mode: {self.semantic_mode}")
        if self.retrieval_policy not in RETRIEVAL_POLICIES:
            raise ValueError(f"unknown retrieval policy: {self.retrieval_policy}")
        object.__setattr__(self, "disabled_subsystems", normalized)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "disabled_subsystems": sorted(self.disabled_subsystems),
                "semantic_mode": self.semantic_mode,
                "retrieval_policy": self.retrieval_policy,
            }
        )


@dataclass(frozen=True)
class BenchmarkMetrics:
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: int = 0
    exact_source_bytes: int = 0
    context_precision_proxy: float | None = None
    context_recall_proxy: float | None = None
    irrelevant_object_admission: int = 0
    wall_ms: float = 0.0
    ingest_ms: float = 0.0
    warm_reconcile_ms: float = 0.0
    provider_calls: int = 0
    failed_strategy_count: int = 0
    repeated_strategy_count: int = 0
    verification_count: int = 0
    mutation_rollback_count: int = 0
    mutation_conflict_count: int = 0

    def __post_init__(self) -> None:
        for field_name in ("input_tokens", "output_tokens"):
            _require_non_negative_int(getattr(self, field_name), field_name, nullable=True)
        for field_name in (
            "tool_calls",
            "exact_source_bytes",
            "irrelevant_object_admission",
            "provider_calls",
            "failed_strategy_count",
            "repeated_strategy_count",
            "verification_count",
            "mutation_rollback_count",
            "mutation_conflict_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        for field_name in ("wall_ms", "ingest_ms", "warm_reconcile_ms"):
            _require_non_negative_number(getattr(self, field_name), field_name)
        for field_name in ("context_precision_proxy", "context_recall_proxy"):
            _require_optional_unit_interval(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class BenchmarkRun:
    spec_fingerprint: str
    arm: BenchmarkArm
    repetition: int
    seed: int
    model_id: str
    scaffold_id: str
    metrics: BenchmarkMetrics
    ablation: AblationConfig = AblationConfig()
    agent_claimed_success: bool | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.spec_fingerprint, "spec_fingerprint")
        _require_non_empty(self.model_id, "model_id")
        _require_non_empty(self.scaffold_id, "scaffold_id")
        if self.arm not in BENCHMARK_ARMS:
            raise ValueError(f"unknown benchmark arm: {self.arm}")
        _require_non_negative_int(self.repetition, "repetition")
        _require_non_negative_int(self.seed, "seed")
        if not isinstance(self.metrics, BenchmarkMetrics):
            raise TypeError("metrics must be BenchmarkMetrics")
        if not isinstance(self.ablation, AblationConfig):
            raise TypeError("ablation must be AblationConfig")
        _require_optional_bool(self.agent_claimed_success, "agent_claimed_success")
        object.__setattr__(self, "evidence_refs", _normalize_evidence_refs(self.evidence_refs))

    @property
    def identity(self) -> str:
        return _fingerprint(
            {
                "spec_fingerprint": self.spec_fingerprint,
                "arm": self.arm,
                "repetition": self.repetition,
                "seed": self.seed,
                "model_id": self.model_id,
                "scaffold_id": self.scaffold_id,
                "ablation_fingerprint": self.ablation.fingerprint,
            }
        )


@dataclass(frozen=True)
class EvaluationResult:
    evaluator_id: str
    success: bool
    regression_free: bool | None = None
    hidden_test_success: bool | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.evaluator_id, "evaluator_id")
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        _require_optional_bool(self.regression_free, "regression_free")
        _require_optional_bool(self.hidden_test_success, "hidden_test_success")
        object.__setattr__(self, "evidence_refs", _normalize_evidence_refs(self.evidence_refs))


@dataclass(frozen=True)
class BenchmarkResult:
    spec: BenchmarkSpec
    run: BenchmarkRun
    evaluation: EvaluationResult

    def __post_init__(self) -> None:
        if not isinstance(self.spec, BenchmarkSpec):
            raise TypeError("spec must be BenchmarkSpec")
        if not isinstance(self.run, BenchmarkRun):
            raise TypeError("run must be BenchmarkRun")
        if not isinstance(self.evaluation, EvaluationResult):
            raise TypeError("evaluation must be EvaluationResult")
        if self.run.spec_fingerprint != self.spec.fingerprint:
            raise ValueError("run spec fingerprint does not match BenchmarkSpec fingerprint")

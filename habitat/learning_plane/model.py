from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any

from ..benchmarking.model import BENCHMARK_CLASSES


CONSTITUTIONAL_LEARNING_TARGETS = frozenset(
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

LEGAL_CANDIDATE_TRANSITIONS = {
    "candidate": frozenset({"shadow", "rejected"}),
    "shadow": frozenset({"experiment", "rejected"}),
    "experiment": frozenset({"evaluated", "rejected"}),
    "evaluated": frozenset({"canary", "rejected"}),
    "canary": frozenset({"promoted", "rejected"}),
    "promoted": frozenset({"rolled_back"}),
    "rejected": frozenset(),
    "rolled_back": frozenset(),
}

_POLICY_FIELDS = frozenset(
    {
        "version",
        "lexical_weight",
        "structural_weight",
        "evidence_weight",
        "graph_depth",
        "max_roots",
        "source_prefetch_budget",
        "abstention_threshold",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _require_sha256(value: object, field_name: str) -> str:
    text = _require_non_empty(value, field_name)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 fingerprint")
    return text


def _require_finite_non_negative_number(
    value: object,
    field_name: str,
    *,
    nullable: bool = False,
) -> int | float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        expected = "number or None" if nullable else "number"
        raise TypeError(f"{field_name} must be {expected}")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return value


def _require_int_range(value: object, field_name: str, lower: int, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if not lower <= value <= upper:
        raise ValueError(f"{field_name} must be in [{lower}, {upper}]")
    return value


def _require_unit_interval(value: object, field_name: str) -> float:
    _require_finite_non_negative_number(value, field_name)
    numeric = float(value)  # type: ignore[arg-type]
    if numeric > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return numeric


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of identifiers")
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of identifiers") from exc
    normalized = tuple(_require_non_empty(item, field_name) for item in items)
    return tuple(sorted(normalized))


def _freeze_json_value(value: object, field_name: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must contain only finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        pairs: list[tuple[str, object]] = []
        for key, item in value.items():
            key_text = _require_non_empty(key, f"{field_name} key")
            pairs.append((key_text, _freeze_json_value(item, field_name)))
        pairs.sort(key=lambda item: item[0])
        return tuple(pairs)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item, field_name) for item in value)
    raise TypeError(f"{field_name} must contain JSON-compatible values")


def _normalize_mapping(value: object, field_name: str) -> tuple[tuple[str, object], ...]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    frozen = _freeze_json_value(value, field_name)
    assert isinstance(frozen, tuple)
    return frozen  # type: ignore[return-value]


def _normalize_resource_metrics(value: object) -> tuple[tuple[str, int | float | None], ...]:
    if not isinstance(value, Mapping):
        raise TypeError("resource_metrics must be a mapping")
    rows: list[tuple[str, int | float | None]] = []
    for key, amount in value.items():
        name = _require_non_empty(key, "resource metric name")
        validated = _require_finite_non_negative_number(
            amount,
            f"resource metric {name}",
            nullable=True,
        )
        rows.append((name, validated))
    rows.sort(key=lambda item: item[0])
    return tuple(rows)


@dataclass(frozen=True)
class ContextPolicy:
    version: str
    lexical_weight: float
    structural_weight: float
    evidence_weight: float
    graph_depth: int
    max_roots: int
    source_prefetch_budget: int
    abstention_threshold: float

    def __post_init__(self) -> None:
        _require_non_empty(self.version, "version")
        for field_name in ("lexical_weight", "structural_weight", "evidence_weight"):
            _require_finite_non_negative_number(getattr(self, field_name), field_name)
        _require_int_range(self.graph_depth, "graph_depth", 0, 8)
        _require_int_range(self.max_roots, "max_roots", 1, 64)
        _require_int_range(
            self.source_prefetch_budget,
            "source_prefetch_budget",
            1,
            200,
        )
        _require_unit_interval(self.abstention_threshold, "abstention_threshold")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ContextPolicy:
        if not isinstance(value, Mapping):
            raise TypeError("learning policy must be a mapping")
        keys = set(value)
        constitutional = keys & CONSTITUTIONAL_LEARNING_TARGETS
        if constitutional:
            raise ValueError(
                "constitutional learning target is not mutable: "
                f"{sorted(constitutional)[0]}"
            )
        unknown = keys - _POLICY_FIELDS
        if unknown:
            raise ValueError(f"unknown learning policy field: {sorted(unknown)[0]}")
        missing = _POLICY_FIELDS - keys
        if missing:
            raise ValueError(f"missing learning policy field: {sorted(missing)[0]}")
        return cls(**dict(value))  # type: ignore[arg-type]

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "lexical_weight": self.lexical_weight,
            "structural_weight": self.structural_weight,
            "evidence_weight": self.evidence_weight,
            "graph_depth": self.graph_depth,
            "max_roots": self.max_roots,
            "source_prefetch_budget": self.source_prefetch_budget,
            "abstention_threshold": self.abstention_threshold,
        }

    @property
    def fingerprint(self) -> str:
        return sha256(_canonical_json(self.canonical_payload)).hexdigest()


@dataclass(frozen=True)
class PolicyCandidate:
    candidate_id: str
    policy_version: str
    policy_fingerprint: str
    baseline_version: str
    baseline_fingerprint: str
    generator_id: str
    state: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.candidate_id, "candidate_id")
        _require_non_empty(self.policy_version, "policy_version")
        _require_sha256(self.policy_fingerprint, "policy_fingerprint")
        _require_non_empty(self.baseline_version, "baseline_version")
        _require_sha256(self.baseline_fingerprint, "baseline_fingerprint")
        _require_non_empty(self.generator_id, "generator_id")
        _require_non_empty(self.created_at, "created_at")
        _require_non_empty(self.updated_at, "updated_at")
        if self.state not in LEGAL_CANDIDATE_TRANSITIONS:
            raise ValueError(f"unknown candidate lifecycle state: {self.state}")


@dataclass(frozen=True)
class EvaluationPacket:
    candidate_id: str
    policy_fingerprint: str
    evaluator_id: str
    heldout_suite_id: str
    baseline_benchmark_fingerprint: str
    candidate_benchmark_fingerprint: str
    improved: bool
    evidence_refs: tuple[str, ...]
    reproduction_tolerance: float | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.candidate_id, "candidate_id")
        _require_sha256(self.policy_fingerprint, "policy_fingerprint")
        _require_non_empty(self.evaluator_id, "evaluator_id")
        _require_non_empty(self.heldout_suite_id, "heldout_suite_id")
        _require_sha256(
            self.baseline_benchmark_fingerprint,
            "baseline_benchmark_fingerprint",
        )
        _require_sha256(
            self.candidate_benchmark_fingerprint,
            "candidate_benchmark_fingerprint",
        )
        if not isinstance(self.improved, bool):
            raise TypeError("improved must be bool")
        refs = _normalize_string_tuple(self.evidence_refs, "evidence_refs")
        if not refs:
            raise ValueError("evidence_refs must not be empty")
        object.__setattr__(self, "evidence_refs", refs)
        tolerance = _require_finite_non_negative_number(
            self.reproduction_tolerance,
            "reproduction_tolerance",
            nullable=True,
        )
        object.__setattr__(self, "reproduction_tolerance", tolerance)

    def require_independent(self, generator_id: str) -> EvaluationPacket:
        generator = _require_non_empty(generator_id, "generator_id")
        if self.evaluator_id == generator:
            raise ValueError("independent evaluator identity must differ from generator identity")
        return self


@dataclass(frozen=True)
class OutcomeRecord:
    policy_version: str
    task_fingerprint: str
    benchmark_class: str
    provider_fingerprints: tuple[str, ...]
    context_refs: tuple[str, ...]
    action_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]
    independent_outcome: tuple[tuple[str, object], ...]
    resource_metrics: tuple[tuple[str, int | float | None], ...]
    errors: tuple[str, ...]
    rollbacks: tuple[str, ...]
    revision: str
    created_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_version, "policy_version")
        _require_non_empty(self.task_fingerprint, "task_fingerprint")
        benchmark_class = _require_non_empty(self.benchmark_class, "benchmark_class")
        if benchmark_class not in BENCHMARK_CLASSES:
            raise ValueError(f"unknown benchmark class: {benchmark_class}")
        _require_non_empty(self.revision, "revision")
        _require_non_empty(self.created_at, "created_at")

        object.__setattr__(
            self,
            "provider_fingerprints",
            _normalize_string_tuple(self.provider_fingerprints, "provider_fingerprints"),
        )
        object.__setattr__(
            self,
            "context_refs",
            _normalize_string_tuple(self.context_refs, "context_refs"),
        )
        object.__setattr__(
            self,
            "action_refs",
            _normalize_string_tuple(self.action_refs, "action_refs"),
        )
        object.__setattr__(
            self,
            "verification_refs",
            _normalize_string_tuple(self.verification_refs, "verification_refs"),
        )
        object.__setattr__(
            self,
            "errors",
            _normalize_string_tuple(self.errors, "errors"),
        )
        object.__setattr__(
            self,
            "rollbacks",
            _normalize_string_tuple(self.rollbacks, "rollbacks"),
        )
        object.__setattr__(
            self,
            "independent_outcome",
            _normalize_mapping(self.independent_outcome, "independent_outcome"),
        )
        object.__setattr__(
            self,
            "resource_metrics",
            _normalize_resource_metrics(self.resource_metrics),
        )

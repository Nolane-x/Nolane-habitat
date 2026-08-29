from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
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

"""Fail-closed operational SLO admission primitives.

Measurements are descriptive evidence. Missing values remain ``None`` and block
admission rather than being coerced into zero or success.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import statistics
from typing import Iterable


def _require_non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_optional_number(value: object, name: str, *, integer: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number or None")
    if integer:
        if not isinstance(value, int):
            raise ValueError(f"{name} must be an integer or None")
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
        return
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number or None")
    if float(value) < 0:
        raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class SloSample:
    scenario_id: str
    completed: bool
    latency_ms: float | None
    peak_memory_bytes: int | None
    baseline_latency_ms: float | None
    baseline_peak_memory_bytes: int | None
    error: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.scenario_id, "scenario_id")
        if type(self.completed) is not bool:
            raise ValueError("completed must be a boolean")
        _require_optional_number(self.latency_ms, "latency_ms")
        _require_optional_number(
            self.peak_memory_bytes, "peak_memory_bytes", integer=True
        )
        _require_optional_number(self.baseline_latency_ms, "baseline_latency_ms")
        _require_optional_number(
            self.baseline_peak_memory_bytes,
            "baseline_peak_memory_bytes",
            integer=True,
        )
        if self.error is not None and not isinstance(self.error, str):
            raise ValueError("error must be a string or None")


@dataclass(frozen=True)
class SloProfile:
    profile_id: str
    required_success_ratio: float
    max_median_regression: float
    max_peak_memory_regression: float
    required_cycles: int

    def __post_init__(self) -> None:
        _require_non_empty_string(self.profile_id, "profile_id")
        for name in (
            "required_success_ratio",
            "max_median_regression",
            "max_peak_memory_regression",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
        if not 0.0 <= float(self.required_success_ratio) <= 1.0:
            raise ValueError("required_success_ratio must be between 0 and 1")
        if float(self.max_median_regression) < 0.0:
            raise ValueError("max_median_regression must be non-negative")
        if float(self.max_peak_memory_regression) < 0.0:
            raise ValueError("max_peak_memory_regression must be non-negative")
        if type(self.required_cycles) is not int or self.required_cycles < 1:
            raise ValueError("required_cycles must be a positive integer")


@dataclass(frozen=True)
class SloReport:
    profile_id: str
    admitted: bool
    total: int
    completed: int
    success_ratio: float
    median_latency_regression: float | None
    peak_memory_regression: float | None
    failures: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["failures"] = list(self.failures)
        value["reasons"] = list(self.reasons)
        return value

    def canonical_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _ratio_regression(current: float, baseline: float) -> float:
    if baseline <= 0.0:
        raise ValueError("baseline must be positive for ratio regression")
    return (current / baseline) - 1.0


def evaluate_slos(profile: SloProfile, samples: Iterable[SloSample]) -> SloReport:
    observed = tuple(samples)
    reasons: set[str] = set()

    if not observed:
        reasons.add("no-samples")

    scenario_ids = [sample.scenario_id for sample in observed]
    duplicates = sorted(
        scenario_id
        for scenario_id in set(scenario_ids)
        if scenario_ids.count(scenario_id) > 1
    )
    reasons.update(f"duplicate-scenario-id:{scenario_id}" for scenario_id in duplicates)

    total = len(observed)
    completed = sum(sample.completed for sample in observed)
    success_ratio = completed / total if total else 0.0

    if total < profile.required_cycles:
        reasons.add("insufficient-cycles")
    if total and success_ratio < profile.required_success_ratio:
        reasons.add("success-ratio")

    failures = tuple(
        sorted(
            f"{sample.scenario_id}: {sample.error or 'incomplete'}"
            for sample in observed
            if not sample.completed
        )
    )

    latency_ready = True
    memory_ready = True
    for sample in observed:
        for field_name in ("latency_ms", "baseline_latency_ms"):
            if getattr(sample, field_name) is None:
                reasons.add(f"missing-measurement:{sample.scenario_id}:{field_name}")
                latency_ready = False
        for field_name in ("peak_memory_bytes", "baseline_peak_memory_bytes"):
            if getattr(sample, field_name) is None:
                reasons.add(f"missing-measurement:{sample.scenario_id}:{field_name}")
                memory_ready = False
        if sample.baseline_latency_ms is not None and sample.baseline_latency_ms <= 0:
            reasons.add(
                f"nonpositive-baseline:{sample.scenario_id}:baseline_latency_ms"
            )
            latency_ready = False
        if (
            sample.baseline_peak_memory_bytes is not None
            and sample.baseline_peak_memory_bytes <= 0
        ):
            reasons.add(
                f"nonpositive-baseline:{sample.scenario_id}:baseline_peak_memory_bytes"
            )
            memory_ready = False

    median_latency_regression: float | None = None
    if observed and latency_ready:
        median_latency_regression = _ratio_regression(
            statistics.median(float(sample.latency_ms) for sample in observed),
            statistics.median(
                float(sample.baseline_latency_ms) for sample in observed
            ),
        )
        if median_latency_regression > profile.max_median_regression:
            reasons.add("median-latency-regression")

    peak_memory_regression: float | None = None
    if observed and memory_ready:
        peak_memory_regression = _ratio_regression(
            float(max(int(sample.peak_memory_bytes) for sample in observed)),
            float(max(int(sample.baseline_peak_memory_bytes) for sample in observed)),
        )
        if peak_memory_regression > profile.max_peak_memory_regression:
            reasons.add("peak-memory-regression")

    ordered_reasons = tuple(sorted(reasons))
    return SloReport(
        profile_id=profile.profile_id,
        admitted=not ordered_reasons,
        total=total,
        completed=completed,
        success_ratio=success_ratio,
        median_latency_regression=median_latency_regression,
        peak_memory_regression=peak_memory_regression,
        failures=failures,
        reasons=ordered_reasons,
    )

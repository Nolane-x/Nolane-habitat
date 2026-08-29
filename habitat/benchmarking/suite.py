from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math

from .model import BENCHMARK_CLASSES, BenchmarkClass, _require_non_empty


BudgetValue = int | float
Budget = tuple[tuple[str, BudgetValue], ...]


def _normalize_budget(value: object) -> Budget:
    if isinstance(value, (str, bytes)):
        raise TypeError("budget must be a mapping or iterable of key/value pairs")

    if isinstance(value, Mapping):
        entries = tuple(value.items())
    else:
        try:
            entries = tuple(value)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError("budget must be a mapping or iterable of key/value pairs") from exc

    normalized: list[tuple[str, BudgetValue]] = []
    seen: set[str] = set()
    for entry in entries:
        if isinstance(entry, (str, bytes)):
            raise TypeError("budget entries must be key/value pairs")
        try:
            key, amount = entry  # type: ignore[misc]
        except (TypeError, ValueError) as exc:
            raise ValueError("budget entries must contain exactly two values") from exc

        key = _require_non_empty(key, "budget key")
        if key in seen:
            raise ValueError(f"duplicate budget key: {key}")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError(f"budget value for {key} must be a number")
        numeric = float(amount)
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError(f"budget value for {key} must be finite and non-negative")
        seen.add(key)
        normalized.append((key, amount))

    normalized.sort(key=lambda item: item[0])
    return tuple(normalized)


def _normalize_tasks(value: object) -> tuple[HeldOutTask, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError("tasks must be an iterable of HeldOutTask")
    try:
        tasks = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError("tasks must be an iterable of HeldOutTask") from exc
    if not tasks:
        raise ValueError("held-out suite requires at least one task")
    for task in tasks:
        if not isinstance(task, HeldOutTask):
            raise TypeError("tasks entries must be HeldOutTask")
    return tasks


@dataclass(frozen=True)
class HeldOutTask:
    task_id: str
    benchmark_class: BenchmarkClass
    prompt: str
    fixture_id: str
    task_fingerprint: str
    repository_revision: str
    budget: Budget = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.task_id, "task_id")
        _require_non_empty(self.prompt, "prompt")
        _require_non_empty(self.fixture_id, "fixture_id")
        _require_non_empty(self.task_fingerprint, "task_fingerprint")
        _require_non_empty(self.repository_revision, "repository_revision")
        if self.benchmark_class not in BENCHMARK_CLASSES:
            raise ValueError(f"unknown benchmark class: {self.benchmark_class}")
        object.__setattr__(self, "budget", _normalize_budget(self.budget))


@dataclass(frozen=True)
class HeldOutSuite:
    suite_id: str
    tasks: tuple[HeldOutTask, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.suite_id, "suite_id")
        tasks = _normalize_tasks(self.tasks)

        task_ids: set[str] = set()
        fingerprints: set[str] = set()
        for task in tasks:
            if task.task_id in task_ids:
                raise ValueError(f"duplicate task_id: {task.task_id}")
            if task.task_fingerprint in fingerprints:
                raise ValueError(f"duplicate task_fingerprint: {task.task_fingerprint}")
            task_ids.add(task.task_id)
            fingerprints.add(task.task_fingerprint)

        object.__setattr__(self, "tasks", tasks)

    @property
    def class_coverage(self) -> tuple[BenchmarkClass, ...]:
        present = {task.benchmark_class for task in self.tasks}
        return tuple(
            benchmark_class
            for benchmark_class in BENCHMARK_CLASSES
            if benchmark_class in present
        )

    @property
    def missing_classes(self) -> tuple[BenchmarkClass, ...]:
        present = {task.benchmark_class for task in self.tasks}
        return tuple(
            benchmark_class
            for benchmark_class in BENCHMARK_CLASSES
            if benchmark_class not in present
        )

    def require_complete_taxonomy(self) -> HeldOutSuite:
        if self.missing_classes:
            missing = ", ".join(self.missing_classes)
            raise ValueError(f"missing benchmark classes: {missing}")
        return self

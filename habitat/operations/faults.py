"""Explicit, deterministic fault points used by reliability tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FaultInjector:
    schedule: dict[str, int]
    counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for point, occurrence in self.schedule.items():
            if not point or occurrence < 1:
                raise ValueError("fault schedule values must be positive occurrences")

    def hit(self, point: str) -> None:
        self.counts[point] = self.counts.get(point, 0) + 1
        if self.schedule.get(point) == self.counts[point]:
            raise RuntimeError(f"injected fault: {point}")

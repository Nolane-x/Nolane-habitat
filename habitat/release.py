from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


REQUIRED_REPORTS = {
    "alpha-candidate": frozenset({"truth-core", "matrix", "faults", "artifacts"}),
    "beta-readiness": frozenset({"semantic", "context", "memory", "privacy"}),
    "beta-candidate": frozenset({"coordination", "mcp-soak", "observatory", "scale"}),
    "production-candidate": frozenset({"security", "slo", "sbom", "reproducibility"}),
}


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    commit: str
    reports: dict[str, str]
    artifact_hashes: dict[str, str]
    residual_risks: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReleaseManifest":
        return cls(
            version=str(value["version"]),
            commit=str(value["commit"]),
            reports={str(key): str(digest) for key, digest in dict(value.get("reports") or {}).items()},
            artifact_hashes={str(key): str(digest) for key, digest in dict(value.get("artifact_hashes") or {}).items()},
            residual_risks=tuple(str(risk) for risk in value.get("residual_risks") or ()),
        )


@dataclass(frozen=True)
class PromotionVerdict:
    target: str
    admitted: bool
    missing_reports: tuple[str, ...]
    failed_gates: tuple[str, ...]
    residual_risks: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_promotion(manifest: ReleaseManifest, target: str) -> PromotionVerdict:
    try:
        required = REQUIRED_REPORTS[target]
    except KeyError as exc:
        raise ValueError(f"unknown promotion target: {target}") from exc
    missing = tuple(sorted(required - manifest.reports.keys()))
    failed = tuple(sorted(name for name in required if not manifest.reports.get(name)))
    return PromotionVerdict(
        target=target,
        admitted=not missing and not failed,
        missing_reports=missing,
        failed_gates=failed,
        residual_risks=manifest.residual_risks,
    )

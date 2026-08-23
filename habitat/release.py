from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping


REQUIRED_REPORTS = {
    "alpha-candidate": frozenset({"truth-core", "matrix", "faults", "artifacts"}),
    "beta-readiness": frozenset({"semantic", "context", "memory", "privacy"}),
    "beta-candidate": frozenset({"coordination", "mcp-soak", "observatory", "scale"}),
    "production-candidate": frozenset({"security", "slo", "sbom", "reproducibility"}),
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionVerdict:
    target: str
    admitted: bool
    missing_reports: tuple[str, ...]
    failed_gates: tuple[str, ...]
    residual_risks: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash_named_files(values: Mapping[str, Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, path in values.items():
        if not name:
            raise ValueError("evidence names must be non-empty")
        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        hashes[str(name)] = _sha256_file(resolved)
    return hashes


def build_release_manifest(
    *,
    version: str,
    commit: str,
    reports: Mapping[str, Path],
    artifacts: Mapping[str, Path],
    residual_risks: tuple[str, ...] = (),
) -> ReleaseManifest:
    return ReleaseManifest(
        version=version,
        commit=commit,
        reports=_hash_named_files(reports),
        artifact_hashes=_hash_named_files(artifacts),
        residual_risks=tuple(residual_risks),
    )


def evaluate_promotion(manifest: ReleaseManifest, target: str) -> PromotionVerdict:
    try:
        required = REQUIRED_REPORTS[target]
    except KeyError as exc:
        raise ValueError(f"unknown promotion target: {target}") from exc
    missing = tuple(sorted(required - manifest.reports.keys()))
    failed = {
        f"report:{name}:invalid-digest"
        for name in required & manifest.reports.keys()
        if not SHA256.fullmatch(manifest.reports[name])
    }
    if "artifacts" in required:
        if not manifest.artifact_hashes:
            failed.add("artifact_hashes:missing")
        else:
            failed.update(
                f"artifact:{name}:invalid-digest"
                for name, digest in manifest.artifact_hashes.items()
                if not SHA256.fullmatch(digest)
            )
    return PromotionVerdict(
        target=target,
        admitted=not missing and not failed,
        missing_reports=missing,
        failed_gates=tuple(sorted(failed)),
        residual_risks=manifest.residual_risks,
    )

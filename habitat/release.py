from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


REQUIRED_REPORTS = {
    "alpha-candidate": frozenset({"truth-core", "matrix", "faults", "artifacts", "scanner", "db-recovery", "mutation-recovery", "reproducible-build", "protocol-conformance", "contract"}),
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
    reviewer_hashes: tuple[str, ...] = ()
    reviewers: dict[str, str] = field(default_factory=dict)
    report_provenance: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReleaseManifest":
        reviewers = {
            str(name): str(digest)
            for name, digest in dict(value.get("reviewers") or {}).items()
        }
        reviewer_hashes = tuple(
            str(digest) for digest in value.get("reviewer_hashes") or ()
        )
        return cls(
            version=str(value["version"]),
            commit=str(value["commit"]),
            reports={str(key): str(digest) for key, digest in dict(value.get("reports") or {}).items()},
            artifact_hashes={str(key): str(digest) for key, digest in dict(value.get("artifact_hashes") or {}).items()},
            residual_risks=tuple(str(risk) for risk in value.get("residual_risks") or ()),
            reviewer_hashes=reviewer_hashes or tuple(reviewers.values()),
            reviewers=reviewers,
            report_provenance={
                str(name): {str(key): str(item) for key, item in dict(record).items()}
                for name, record in dict(value.get("report_provenance") or {}).items()
                if isinstance(record, Mapping)
            },
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


def _canonical_report_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _report_provenance(values: Mapping[str, Path]) -> dict[str, dict[str, str]]:
    provenance: dict[str, dict[str, str]] = {}
    for name, path in values.items():
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, Mapping):
            continue
        source_commit = value.get("source_commit")
        status = value.get("status")
        reported_digest = value.get("report_sha256")
        unsigned = {key: item for key, item in value.items() if key != "report_sha256"}
        if (
            not isinstance(source_commit, str)
            or not isinstance(status, str)
            or not isinstance(reported_digest, str)
            or not SHA256.fullmatch(reported_digest)
            or reported_digest != _canonical_report_digest(unsigned)
        ):
            continue
        provenance[str(name)] = {
            "source_commit": source_commit,
            "status": status,
            "report_sha256": reported_digest,
        }
    return provenance


def build_release_manifest(
    *,
    version: str,
    commit: str,
    reports: Mapping[str, Path],
    artifacts: Mapping[str, Path],
    residual_risks: tuple[str, ...] = (),
    reviewers: Mapping[str, Path] | None = None,
) -> ReleaseManifest:
    reviewer_records = _hash_named_files(reviewers or {})
    return ReleaseManifest(
        version=version,
        commit=commit,
        reports=_hash_named_files(reports),
        artifact_hashes=_hash_named_files(artifacts),
        residual_risks=tuple(residual_risks),
        reviewer_hashes=tuple(reviewer_records.values()),
        reviewers=reviewer_records,
        report_provenance=_report_provenance(reports),
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
    if target == "alpha-candidate":
        if not re.fullmatch(r"[0-9a-f]{40}", manifest.commit):
            failed.add("manifest:commit:invalid-sha")
        for name in required & manifest.reports.keys():
            provenance = manifest.report_provenance.get(name)
            if not provenance:
                failed.add(f"report:{name}:provenance:missing-or-invalid")
                continue
            if provenance.get("source_commit") != manifest.commit:
                failed.add(f"report:{name}:source-commit-mismatch")
            if provenance.get("status") != "passed":
                failed.add(f"report:{name}:status")
            if not SHA256.fullmatch(provenance.get("report_sha256", "")):
                failed.add(f"report:{name}:report-hash-invalid")
        if not manifest.reviewer_hashes:
            failed.add("reviewer_hashes:missing")
        else:
            if any(not SHA256.fullmatch(digest) for digest in manifest.reviewer_hashes):
                failed.add("reviewer_hashes:invalid-digest")
            evidence_hashes = set(manifest.reports.values()) | set(manifest.artifact_hashes.values())
            if any(digest in evidence_hashes for digest in manifest.reviewer_hashes):
                failed.add("reviewer_hashes:not-independent")
        if manifest.reviewers:
            if any(not name or not SHA256.fullmatch(digest) for name, digest in manifest.reviewers.items()):
                failed.add("reviewers:invalid-record")
            if set(manifest.reviewers.values()) != set(manifest.reviewer_hashes):
                failed.add("reviewers:hash-mismatch")
    return PromotionVerdict(
        target=target,
        admitted=not missing and not failed,
        missing_reports=missing,
        failed_gates=tuple(sorted(failed)),
        residual_risks=manifest.residual_risks,
    )

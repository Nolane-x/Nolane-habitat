from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
import hashlib
import json
import math
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
PROVENANCE_FIELDS = frozenset(
    {"schema", "source_commit", "status", "report_sha256", "evidence_type"}
)


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    commit: str
    reports: dict[str, str]
    artifact_hashes: dict[str, str]
    residual_risks: tuple[str, ...]
    reviewer_hashes: tuple[str, ...] = ()
    reviewers: dict[str, str] = field(default_factory=dict)
    report_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    review_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    manifest_sha256: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReleaseManifest":
        if not isinstance(value, Mapping):
            raise ValueError("manifest must be an object")
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(str(key) for key in value if key not in allowed)
        if unknown:
            raise ValueError(f"manifest has unknown fields: {', '.join(unknown)}")
        reviewers = _string_mapping(value.get("reviewers", {}), "reviewers")
        reviewer_hashes = _string_sequence(
            value.get("reviewer_hashes", []), "reviewer_hashes"
        )
        return cls(
            version=_required_string(value, "version", "manifest"),
            commit=_required_string(value, "commit", "manifest"),
            reports=_string_mapping(value.get("reports", {}), "reports"),
            artifact_hashes=_string_mapping(
                value.get("artifact_hashes", {}), "artifact_hashes"
            ),
            residual_risks=_string_sequence(
                value.get("residual_risks", []), "residual_risks"
            ),
            reviewer_hashes=reviewer_hashes or tuple(reviewers.values()),
            reviewers=reviewers,
            report_provenance=_provenance_mapping(
                value.get("report_provenance", {}), "report_provenance"
            ),
            review_provenance=_provenance_mapping(
                value.get("review_provenance", {}), "review_provenance"
            ),
            manifest_sha256=_optional_string(value.get("manifest_sha256", ""), "manifest_sha256"),
        )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["residual_risks"] = list(self.residual_risks)
        value["reviewer_hashes"] = list(self.reviewer_hashes)
        return value


@dataclass(frozen=True)
class PromotionVerdict:
    target: str
    admitted: bool
    missing_reports: tuple[str, ...]
    failed_gates: tuple[str, ...]
    residual_risks: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_string(value: Mapping[str, Any], name: str, context: str) -> str:
    item = value.get(name)
    if not isinstance(item, str):
        raise ValueError(f"{context}.{name} must be a string")
    return item


def _optional_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _string_mapping(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str):
            raise ValueError(f"{name} must map non-empty strings to strings")
        result[key] = item
    return result


def _string_sequence(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(value)


def _provenance_mapping(value: Any, name: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    records: dict[str, dict[str, Any]] = {}
    for evidence_name, record in value.items():
        if not isinstance(evidence_name, str) or not evidence_name or not isinstance(record, Mapping):
            raise ValueError(f"{name} must map non-empty names to objects")
        unknown = sorted(str(key) for key in record if key not in PROVENANCE_FIELDS)
        if unknown:
            raise ValueError(
                f"{name}.{evidence_name} has unknown fields: {', '.join(unknown)}"
            )
        source_commit = _required_string(record, "source_commit", name)
        status = _required_string(record, "status", name)
        report_sha256 = _required_string(record, "report_sha256", name)
        evidence_type = _required_string(record, "evidence_type", name)
        schema = record.get("schema")
        if type(schema) is not int or schema < 1:
            raise ValueError(f"{name}.schema must be a positive integer")
        records[evidence_name] = {
            "source_commit": source_commit,
            "status": status,
            "report_sha256": report_sha256,
            "evidence_type": evidence_type,
            "schema": schema,
        }
    return records


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _parse_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite JSON number")
    return number


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def load_json_object(raw: bytes, *, context: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_float=_parse_json_float,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{context}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _read_named_files(values: Mapping[str, Path]) -> dict[str, bytes]:
    snapshots: dict[str, bytes] = {}
    for name, path in values.items():
        if not isinstance(name, str) or not name:
            raise ValueError("evidence names must be non-empty")
        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        snapshots[name] = resolved.read_bytes()
    return snapshots


def _hash_named_files(values: Mapping[str, Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, path in values.items():
        if not isinstance(name, str) or not name:
            raise ValueError("evidence names must be non-empty")
        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes[name] = digest.hexdigest()
    return hashes


def _canonical_report_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def canonical_report_sha256(value: Mapping[str, Any]) -> str:
    return _canonical_report_digest(value)


def _canonical_manifest_digest(value: Mapping[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "manifest_sha256"}
    return _canonical_report_digest(unsigned)


def _report_provenance(
    snapshots: Mapping[str, bytes], *, context: str
) -> dict[str, dict[str, Any]]:
    provenance: dict[str, dict[str, Any]] = {}
    for name, snapshot in snapshots.items():
        value = load_json_object(snapshot, context=f"{context}:{name}")
        schema = value.get("schema")
        source_commit = value.get("source_commit")
        status = value.get("status")
        reported_digest = value.get("report_sha256")
        evidence_type = value.get("evidence_type", "")
        unsigned = {key: item for key, item in value.items() if key != "report_sha256"}
        if (
            type(schema) is not int
            or schema < 1
            or not isinstance(source_commit, str)
            or not isinstance(status, str)
            or not isinstance(reported_digest, str)
            or not isinstance(evidence_type, str)
            or not SHA256.fullmatch(reported_digest)
            or reported_digest != _canonical_report_digest(unsigned)
        ):
            continue
        provenance[str(name)] = {
            "source_commit": source_commit,
            "status": status,
            "report_sha256": reported_digest,
            "evidence_type": evidence_type,
            "schema": schema,
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
    report_snapshots = _read_named_files(reports)
    review_snapshots = _read_named_files(reviewers or {})
    reviewer_records = {
        name: hashlib.sha256(snapshot).hexdigest()
        for name, snapshot in sorted(review_snapshots.items())
    }
    manifest = ReleaseManifest(
        version=version,
        commit=commit,
        reports={
            name: hashlib.sha256(snapshot).hexdigest()
            for name, snapshot in report_snapshots.items()
        },
        artifact_hashes=_hash_named_files(artifacts),
        residual_risks=tuple(residual_risks),
        reviewer_hashes=tuple(reviewer_records[name] for name in sorted(reviewer_records)),
        reviewers=reviewer_records,
        report_provenance=_report_provenance(report_snapshots, context="report"),
        review_provenance=_report_provenance(review_snapshots, context="review"),
    )
    return replace(
        manifest,
        manifest_sha256=_canonical_manifest_digest(manifest.as_dict()),
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
    if set(manifest.reports) != required:
        failed.add("reports:required-set-mismatch")
    if (
        not SHA256.fullmatch(manifest.manifest_sha256)
        or manifest.manifest_sha256 != _canonical_manifest_digest(manifest.as_dict())
    ):
        failed.add("manifest:self-hash:invalid")
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
        if provenance.get("evidence_type") not in ("", "report"):
            failed.add(f"report:{name}:invalid-kind")
        if not SHA256.fullmatch(provenance.get("report_sha256", "")):
            failed.add(f"report:{name}:report-hash-invalid")
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
        if not manifest.reviewer_hashes:
            failed.add("reviewer_hashes:missing")
        else:
            if any(not SHA256.fullmatch(digest) for digest in manifest.reviewer_hashes):
                failed.add("reviewer_hashes:invalid-digest")
            evidence_hashes = set(manifest.reports.values()) | set(manifest.artifact_hashes.values())
            if any(digest in evidence_hashes for digest in manifest.reviewer_hashes):
                failed.add("reviewer_hashes:reused-evidence")
        if manifest.reviewers:
            if any(not name or not SHA256.fullmatch(digest) for name, digest in manifest.reviewers.items()):
                failed.add("reviewers:invalid-record")
            if set(manifest.reviewers.values()) != set(manifest.reviewer_hashes):
                failed.add("reviewers:hash-mismatch")
        else:
            failed.add("reviewers:missing")
        for name in manifest.reviewers:
            provenance = manifest.review_provenance.get(name)
            if not provenance:
                failed.add(f"review:{name}:provenance:missing-or-invalid")
                continue
            if provenance.get("source_commit") != manifest.commit:
                failed.add(f"review:{name}:source-commit-mismatch")
            if provenance.get("status") != "passed":
                failed.add(f"review:{name}:status")
            if (
                provenance.get("schema") != 1
                or provenance.get("evidence_type") != "review"
            ):
                failed.add(f"review:{name}:invalid-kind")
            if not SHA256.fullmatch(provenance.get("report_sha256", "")):
                failed.add(f"review:{name}:report-hash-invalid")
            if provenance.get("report_sha256") in {
                item.get("report_sha256") for item in manifest.report_provenance.values()
            }:
                failed.add(f"review:{name}:reused-report-payload")
    return PromotionVerdict(
        target=target,
        admitted=not missing and not failed,
        missing_reports=missing,
        failed_gates=tuple(sorted(failed)),
        residual_risks=manifest.residual_risks,
    )

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_LOCATION_FIELDS = frozenset({"start_line", "end_line", "start_column", "end_column"})
_VALID_TRUST = frozenset({"exact", "semantic", "parser", "heuristic", "derived"})
_VALID_KINDS = frozenset({"presence-conflict", "attribute-conflict", "location-conflict", "relation-conflict"})


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("semantic claim value must be finite JSON-compatible data") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class SemanticClaim:
    id: str
    subject_key: str
    capability: str
    provider_id: str
    provider_fingerprint: str | None
    revision: str
    path: str
    source_digest: str
    trust: str
    value: Any
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class SemanticDisagreementRecord:
    id: str
    subject_key: str
    capability: str
    revision: str
    path: str
    source_digest: str
    kind: str
    claims: tuple[SemanticClaim, ...]
    missing_providers: tuple[str, ...]
    comparison_complete: bool
    resolution: str = "unresolved"

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(f"unknown semantic disagreement kind: {self.kind}")
        if self.resolution != "unresolved":
            raise ValueError("semantic disagreements are unresolved in this wave")


def make_claim(
    *,
    subject_key: str,
    capability: str,
    provider_id: str,
    provider_fingerprint: str | None,
    revision: str,
    path: str,
    source_digest: str,
    trust: str,
    value: Any,
    evidence: Sequence[str] = (),
) -> SemanticClaim:
    subject_key = _required_text(subject_key, "subject_key")
    capability = _required_text(capability, "capability")
    provider_id = _required_text(provider_id, "provider_id")
    revision = _required_text(revision, "revision")
    path = _required_text(path, "path")
    source_digest = _required_text(source_digest, "source_digest")
    trust = _required_text(trust, "trust")
    if trust not in _VALID_TRUST:
        raise ValueError(f"unknown semantic claim trust: {trust}")
    if provider_fingerprint is not None:
        provider_fingerprint = _required_text(provider_fingerprint, "provider_fingerprint")
    canonical_value = json.loads(_canonical_json(value))
    normalized_evidence = tuple(
        item.strip() for item in evidence if isinstance(item, str) and item.strip()
    )
    claim_id = _sha256({
        "subject_key": subject_key,
        "capability": capability,
        "provider_id": provider_id,
        "provider_fingerprint": provider_fingerprint,
        "revision": revision,
        "path": path,
        "source_digest": source_digest,
        "trust": trust,
        "value": canonical_value,
        "evidence": list(normalized_evidence),
    })
    return SemanticClaim(
        id=claim_id,
        subject_key=subject_key,
        capability=capability,
        provider_id=provider_id,
        provider_fingerprint=provider_fingerprint,
        revision=revision,
        path=path,
        source_digest=source_digest,
        trust=trust,
        value=canonical_value,
        evidence=normalized_evidence,
    )


def _location_only_difference(values: list[Any]) -> bool:
    if not values or not all(isinstance(value, dict) and value.get("kind") == "symbol" for value in values):
        return False
    baseline = dict(values[0])
    baseline_location = {key: baseline.pop(key, None) for key in _LOCATION_FIELDS}
    saw_location_difference = False
    for raw in values[1:]:
        current = dict(raw)
        current_location = {key: current.pop(key, None) for key in _LOCATION_FIELDS}
        if current != baseline:
            return False
        if current_location != baseline_location:
            saw_location_difference = True
    return saw_location_difference


def _conflict_kind(claims: tuple[SemanticClaim, ...]) -> str:
    values = [claim.value for claim in claims]
    if _location_only_difference(values):
        return "location-conflict"
    if any(isinstance(value, dict) and value.get("kind") == "relation" for value in values):
        return "relation-conflict"
    return "attribute-conflict"


def _record(
    *,
    kind: str,
    subject_key: str,
    claims: tuple[SemanticClaim, ...],
    missing_providers: tuple[str, ...],
    comparison_complete: bool,
) -> SemanticDisagreementRecord:
    if not claims:
        raise ValueError("semantic disagreement requires at least one positive claim")
    ordered_claims = tuple(sorted(claims, key=lambda claim: claim.id))
    first = ordered_claims[0]
    for claim in ordered_claims[1:]:
        if (
            claim.subject_key != subject_key
            or claim.capability != first.capability
            or claim.revision != first.revision
            or claim.path != first.path
            or claim.source_digest != first.source_digest
        ):
            raise ValueError("semantic disagreement claims must share subject and source provenance")
    missing_providers = tuple(sorted(set(missing_providers)))
    record_id = _sha256({
        "subject_key": subject_key,
        "capability": first.capability,
        "revision": first.revision,
        "path": first.path,
        "source_digest": first.source_digest,
        "kind": kind,
        "claim_ids": [claim.id for claim in ordered_claims],
        "missing_providers": list(missing_providers),
        "comparison_complete": bool(comparison_complete),
        "resolution": "unresolved",
    })
    return SemanticDisagreementRecord(
        id=record_id,
        subject_key=subject_key,
        capability=first.capability,
        revision=first.revision,
        path=first.path,
        source_digest=first.source_digest,
        kind=kind,
        claims=ordered_claims,
        missing_providers=missing_providers,
        comparison_complete=bool(comparison_complete),
    )


def compare_claims(
    claims_by_provider: Mapping[str, Sequence[SemanticClaim]],
    *,
    comparison_complete: bool,
    max_disagreements: int = 2000,
) -> dict[str, Any]:
    if isinstance(max_disagreements, bool) or not isinstance(max_disagreements, int) or max_disagreements < 1:
        raise ValueError("max_disagreements must be a positive integer")
    if not isinstance(claims_by_provider, Mapping):
        raise TypeError("claims_by_provider must be a mapping")

    provider_ids = tuple(sorted(_required_text(provider_id, "provider_id") for provider_id in claims_by_provider))
    grouped: dict[str, dict[str, list[SemanticClaim]]] = {}
    for provider_id in provider_ids:
        provider_claims = claims_by_provider[provider_id]
        if not isinstance(provider_claims, Sequence):
            raise TypeError("provider claims must be a sequence")
        for claim in provider_claims:
            if not isinstance(claim, SemanticClaim):
                raise TypeError("provider claims must contain SemanticClaim values")
            if claim.provider_id != provider_id:
                raise ValueError("semantic claim provider_id does not match mapping key")
            grouped.setdefault(claim.subject_key, {}).setdefault(provider_id, []).append(claim)

    disagreements: list[SemanticDisagreementRecord] = []
    truncated = False
    for subject_key in sorted(grouped):
        by_provider = grouped[subject_key]
        present_providers = set(by_provider)
        missing = tuple(provider_id for provider_id in provider_ids if provider_id not in present_providers)
        positive_claims = tuple(
            claim
            for provider_id in provider_ids
            for claim in sorted(by_provider.get(provider_id, ()), key=lambda item: item.id)
        )

        if missing:
            if comparison_complete and positive_claims:
                disagreements.append(_record(
                    kind="presence-conflict",
                    subject_key=subject_key,
                    claims=positive_claims,
                    missing_providers=missing,
                    comparison_complete=True,
                ))
        else:
            value_hashes = {_sha256(claim.value) for claim in positive_claims}
            if len(value_hashes) > 1:
                disagreements.append(_record(
                    kind=_conflict_kind(positive_claims),
                    subject_key=subject_key,
                    claims=positive_claims,
                    missing_providers=(),
                    comparison_complete=bool(comparison_complete),
                ))

        if len(disagreements) >= max_disagreements:
            remaining_subjects = any(key > subject_key for key in grouped)
            truncated = remaining_subjects
            break

    disagreements.sort(key=lambda item: item.id)
    return {
        "comparison_complete": bool(comparison_complete),
        "provider_ids": list(provider_ids),
        "disagreements": disagreements,
        "count": len(disagreements),
        "truncated": truncated,
    }


__all__ = [
    "SemanticClaim",
    "SemanticDisagreementRecord",
    "compare_claims",
    "make_claim",
]

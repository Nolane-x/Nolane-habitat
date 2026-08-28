from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .authority import AuthorityClass


def _normalize_json(value: Any) -> Any:
    """Return a detached JSON-compatible value and reject non-finite/unsupported data."""

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return json.loads(encoded)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(value[key]) for key in sorted(value)})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _authority(value: AuthorityClass | str | None, *, field: str, allow_none: bool) -> AuthorityClass | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field} is required")
    if isinstance(value, AuthorityClass):
        return value
    try:
        return AuthorityClass(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unknown {field}: {value!r}") from exc


@dataclass(frozen=True)
class TruthClaim:
    id: str
    subject: str
    predicate: str
    value: Any
    value_digest: str
    authority_class: AuthorityClass
    trust: str | None
    confidence: float | None
    revision: str
    path: str | None
    source_digest: str | None
    producer: str
    provider_fingerprint: str | None
    observed_at: str | None
    origin_claim_id: str | None
    origin_authority_class: AuthorityClass | None
    provenance: Mapping[str, Any]

    def canonical_value(self) -> Any:
        return _thaw_json(self.value)

    def canonical_provenance(self) -> dict[str, Any]:
        return _thaw_json(self.provenance)


def make_truth_claim(
    *,
    subject: str,
    predicate: str,
    value: Any,
    authority_class: AuthorityClass | str,
    revision: str,
    producer: str,
    trust: str | None = None,
    confidence: float | None = None,
    path: str | None = None,
    source_digest: str | None = None,
    provider_fingerprint: str | None = None,
    observed_at: str | None = None,
    origin_claim_id: str | None = None,
    origin_authority_class: AuthorityClass | str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> TruthClaim:
    if not isinstance(subject, str) or not subject:
        raise ValueError("claim subject must be a non-empty string")
    if not isinstance(predicate, str) or not predicate:
        raise ValueError("claim predicate must be a non-empty string")
    if not isinstance(revision, str) or not revision:
        raise ValueError("claim revision must be a non-empty string")
    if not isinstance(producer, str) or not producer:
        raise ValueError("claim producer must be a non-empty string")
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise TypeError("claim confidence must be numeric or None")
        if not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("claim confidence must be between 0 and 1")
        confidence = float(confidence)

    authority = _authority(authority_class, field="authority_class", allow_none=False)
    origin_authority = _authority(
        origin_authority_class,
        field="origin_authority_class",
        allow_none=True,
    )
    normalized_value = _normalize_json(value)
    normalized_provenance = _normalize_json(dict(provenance or {}))
    value_digest = hashlib.sha256(_canonical_bytes(normalized_value)).hexdigest()

    identity = {
        "subject": subject,
        "predicate": predicate,
        "value": normalized_value,
        "authority_class": authority.value,
        "trust": trust,
        "revision": revision,
        "path": path,
        "source_digest": source_digest,
        "producer": producer,
        "provider_fingerprint": provider_fingerprint,
        "observed_at": observed_at,
        "origin_claim_id": origin_claim_id,
        "origin_authority_class": origin_authority.value if origin_authority is not None else None,
        "provenance": normalized_provenance,
    }
    claim_id = "truth-" + hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    return TruthClaim(
        id=claim_id,
        subject=subject,
        predicate=predicate,
        value=_freeze_json(normalized_value),
        value_digest=value_digest,
        authority_class=authority,
        trust=trust,
        confidence=confidence,
        revision=revision,
        path=path,
        source_digest=source_digest,
        producer=producer,
        provider_fingerprint=provider_fingerprint,
        observed_at=observed_at,
        origin_claim_id=origin_claim_id,
        origin_authority_class=origin_authority,
        provenance=_freeze_json(normalized_provenance),
    )


__all__ = ["TruthClaim", "make_truth_claim"]

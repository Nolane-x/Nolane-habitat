from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .authority import AuthorityClass
from .claims import TruthClaim


def _stable_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def _required_revision(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("current_revision must be a non-empty string")
    return value


def _current_digest(current_digests: Mapping[str, str | None], path: str) -> str | None:
    value = current_digests.get(path)
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True)
class StaleClaimRecord:
    id: str
    claim_id: str
    subject: str
    predicate: str
    revision: str
    path: str | None
    current_revision: str
    current_source_digest: str | None
    reasons: tuple[str, ...]
    status: str = "stale"

    def __post_init__(self) -> None:
        if self.status != "stale":
            raise ValueError("stale claim records must remain stale")
        if not self.reasons:
            raise ValueError("stale claim records require at least one reason")


@dataclass(frozen=True)
class TruthContradictionRecord:
    id: str
    claim_ids: tuple[str, ...]
    subject: str
    predicate: str
    revision: str
    authority_classes: tuple[AuthorityClass, ...]
    status: str = "unresolved"
    reason: str = "current claims disagree on canonical value"

    def __post_init__(self) -> None:
        if self.status != "unresolved":
            raise ValueError("truth contradictions are unresolved in this wave")
        if len(self.claim_ids) < 2:
            raise ValueError("truth contradiction requires at least two claims")


def claim_staleness(
    claim: TruthClaim,
    *,
    current_revision: str,
    current_digests: Mapping[str, str | None],
) -> StaleClaimRecord | None:
    if not isinstance(claim, TruthClaim):
        raise TypeError("claim must be a TruthClaim")
    current_revision = _required_revision(current_revision)
    if not isinstance(current_digests, Mapping):
        raise TypeError("current_digests must be a mapping")

    reasons: list[str] = []
    if claim.revision != current_revision:
        reasons.append("revision-mismatch")

    current_source_digest: str | None = None
    if claim.path is not None and claim.source_digest is not None:
        current_source_digest = _current_digest(current_digests, claim.path)
        if current_source_digest is None:
            reasons.append("source-digest-unavailable")
        elif current_source_digest != claim.source_digest:
            reasons.append("source-digest-mismatch")

    if not reasons:
        return None

    normalized_reasons = tuple(reasons)
    record_id = _stable_id(
        "stale-",
        {
            "claim_id": claim.id,
            "current_revision": current_revision,
            "current_source_digest": current_source_digest,
            "reasons": list(normalized_reasons),
            "status": "stale",
        },
    )
    return StaleClaimRecord(
        id=record_id,
        claim_id=claim.id,
        subject=claim.subject,
        predicate=claim.predicate,
        revision=claim.revision,
        path=claim.path,
        current_revision=current_revision,
        current_source_digest=current_source_digest,
        reasons=normalized_reasons,
    )


def _contradiction(claims: tuple[TruthClaim, ...]) -> TruthContradictionRecord:
    ordered = tuple(sorted(claims, key=lambda item: item.id))
    first = ordered[0]
    claim_ids = tuple(item.id for item in ordered)
    authority_classes = tuple(
        sorted({item.authority_class for item in ordered}, key=lambda authority: authority.value)
    )
    reason = "current claims disagree on canonical value"
    record_id = _stable_id(
        "contradiction-",
        {
            "claim_ids": list(claim_ids),
            "subject": first.subject,
            "predicate": first.predicate,
            "revision": first.revision,
            "authority_classes": [authority.value for authority in authority_classes],
            "status": "unresolved",
            "reason": reason,
        },
    )
    return TruthContradictionRecord(
        id=record_id,
        claim_ids=claim_ids,
        subject=first.subject,
        predicate=first.predicate,
        revision=first.revision,
        authority_classes=authority_classes,
        reason=reason,
    )


def project_truth(
    claims: Iterable[TruthClaim],
    *,
    current_revision: str,
    current_digests: Mapping[str, str | None],
    max_claims: int = 500,
) -> dict[str, Any]:
    current_revision = _required_revision(current_revision)
    if not isinstance(current_digests, Mapping):
        raise TypeError("current_digests must be a mapping")
    if isinstance(max_claims, bool) or not isinstance(max_claims, int) or max_claims < 1:
        raise ValueError("max_claims must be a positive integer")

    try:
        materialized = tuple(claims)
    except TypeError as exc:
        raise TypeError("claims must be iterable") from exc
    if any(not isinstance(claim, TruthClaim) for claim in materialized):
        raise TypeError("claims must contain only TruthClaim values")

    # A repeated copy of one immutable claim is still one piece of evidence. Deduplicate before
    # bounding so duplicate input cannot become an accidental vote or alter deterministic output.
    unique_by_id = {claim.id: claim for claim in materialized}
    ordered = tuple(unique_by_id[claim_id] for claim_id in sorted(unique_by_id))
    input_claim_count = len(ordered)
    selected = ordered[:max_claims]
    truncated = input_claim_count > len(selected)

    stale_records: list[StaleClaimRecord] = []
    current_claims: list[TruthClaim] = []
    for claim in selected:
        stale = claim_staleness(
            claim,
            current_revision=current_revision,
            current_digests=current_digests,
        )
        if stale is None:
            current_claims.append(claim)
        else:
            stale_records.append(stale)

    grouped: dict[tuple[str, str, str], list[TruthClaim]] = {}
    for claim in current_claims:
        grouped.setdefault((claim.subject, claim.predicate, claim.revision), []).append(claim)

    contradictions: list[TruthContradictionRecord] = []
    for key in sorted(grouped):
        group = tuple(grouped[key])
        if len({claim.value_digest for claim in group}) > 1:
            contradictions.append(_contradiction(group))

    stale_records.sort(key=lambda item: item.id)
    contradictions.sort(key=lambda item: item.id)
    return {
        "claims": selected,
        "stale_claims": tuple(stale_records),
        "contradictions": tuple(contradictions),
        "input_claim_count": input_claim_count,
        "claim_count": len(selected),
        "stale_count": len(stale_records),
        "contradiction_count": len(contradictions),
        "truncated": truncated,
    }


__all__ = [
    "StaleClaimRecord",
    "TruthContradictionRecord",
    "claim_staleness",
    "project_truth",
]

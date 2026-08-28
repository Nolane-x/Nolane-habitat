from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class AuthorityClass(str, Enum):
    """Categorical evidence authority.

    Authority is intentionally not ordered. Callers must declare the exact
    classes accepted for an operation instead of comparing strength scores.
    """

    SOURCE_EXACT = "SOURCE_EXACT"
    OBSERVED_EXACT = "OBSERVED_EXACT"
    COMPILER_PRECISE = "COMPILER_PRECISE"
    PARSER_DERIVED = "PARSER_DERIVED"
    HEURISTIC_DERIVED = "HEURISTIC_DERIVED"
    MODEL_INFERRED = "MODEL_INFERRED"
    MEMORY_RECALLED = "MEMORY_RECALLED"


_LEGACY_TRUST_AUTHORITY: dict[str, AuthorityClass] = {
    "exact": AuthorityClass.SOURCE_EXACT,
    "semantic": AuthorityClass.COMPILER_PRECISE,
    "parser": AuthorityClass.PARSER_DERIVED,
    "heuristic": AuthorityClass.HEURISTIC_DERIVED,
    "derived": AuthorityClass.HEURISTIC_DERIVED,
}


def legacy_authority(trust: str | None) -> AuthorityClass | None:
    """Conservatively adapt one legacy trust grade into categorical authority."""

    if not isinstance(trust, str) or not trust:
        return None
    return _LEGACY_TRUST_AUTHORITY.get(trust)


AuthorityMode = Literal["direct-source", "evidence-anchor"]


@dataclass(frozen=True)
class OperationAuthorityDeclaration:
    operation: str
    mode: AuthorityMode
    accepted_evidence_authorities: frozenset[AuthorityClass]
    requires_canonical_source: bool
    requires_source_digest: bool
    rationale: str


_OPERATION_AUTHORITY: dict[str, OperationAuthorityDeclaration] = {
    "replace_text": OperationAuthorityDeclaration(
        operation="replace_text",
        mode="direct-source",
        accepted_evidence_authorities=frozenset(),
        requires_canonical_source=True,
        requires_source_digest=True,
        rationale="Direct text replacement is authorized by canonical source plus a digest-bound anchor, not derived evidence.",
    ),
    "replace_span": OperationAuthorityDeclaration(
        operation="replace_span",
        mode="direct-source",
        accepted_evidence_authorities=frozenset(),
        requires_canonical_source=True,
        requires_source_digest=True,
        rationale="Direct span replacement is authorized by canonical source plus digest/text anchors.",
    ),
    "replace_symbol_source": OperationAuthorityDeclaration(
        operation="replace_symbol_source",
        mode="evidence-anchor",
        accepted_evidence_authorities=frozenset({AuthorityClass.SOURCE_EXACT}),
        requires_canonical_source=True,
        requires_source_digest=True,
        rationale="A derived symbol anchor may authorize replacement only when it is exact-source authority and current source checks still pass.",
    ),
    "create_file": OperationAuthorityDeclaration(
        operation="create_file",
        mode="direct-source",
        accepted_evidence_authorities=frozenset(),
        requires_canonical_source=True,
        requires_source_digest=False,
        rationale="File creation is governed by workspace source authority and policy; no pre-existing evidence anchor exists.",
    ),
    "delete_file": OperationAuthorityDeclaration(
        operation="delete_file",
        mode="direct-source",
        accepted_evidence_authorities=frozenset(),
        requires_canonical_source=True,
        requires_source_digest=True,
        rationale="File deletion is authorized against current canonical source with a digest binding.",
    ),
    "move_file": OperationAuthorityDeclaration(
        operation="move_file",
        mode="direct-source",
        accepted_evidence_authorities=frozenset(),
        requires_canonical_source=True,
        requires_source_digest=True,
        rationale="File movement is authorized against current canonical source with a digest binding.",
    ),
}


def operation_authority(operation: str) -> OperationAuthorityDeclaration:
    """Return the explicit authority contract for a supported mutation operation."""

    try:
        return _OPERATION_AUTHORITY[operation]
    except KeyError as exc:
        raise KeyError(f"unknown mutation operation authority declaration: {operation}") from exc


def operation_allows_evidence(operation: str, authority: AuthorityClass | None) -> bool:
    """Return whether an evidence anchor of exactly this class may authorize the operation."""

    declaration = operation_authority(operation)
    if declaration.mode != "evidence-anchor" or authority is None:
        return False
    return authority in declaration.accepted_evidence_authorities


__all__ = [
    "AuthorityClass",
    "OperationAuthorityDeclaration",
    "legacy_authority",
    "operation_allows_evidence",
    "operation_authority",
]

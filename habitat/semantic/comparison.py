from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..compiler import MAX_PARSE_BYTES
from ..util import detect_language, sha256_bytes, sha256_file, stable_id
from .admission import SemanticAdmissionRegistry
from .base import SemanticParseResult
from .disagreement import SemanticClaim, compare_claims, make_claim


DEFAULT_MAX_PROVIDERS = 4
DEFAULT_MAX_CLAIMS = 5_000
DEFAULT_MAX_DISAGREEMENTS = 2_000
_PROVIDER_REASON_LIMIT = 500


class SemanticComparisonStaleError(RuntimeError):
    """Raised when source or revision truth changes during one semantic comparison."""


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bounded_reason(value: object) -> str:
    text = str(value or "")
    return text[:_PROVIDER_REASON_LIMIT]


def _resolve_source(root: Path, path: Path) -> tuple[Path, str]:
    resolved_root = Path(root).resolve()
    raw = Path(path)
    resolved = raw.resolve() if raw.is_absolute() else (resolved_root / raw).resolve()
    try:
        relative = resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"semantic comparison path escapes source root: {path}") from exc
    if not relative or relative == "." or not resolved.is_file():
        raise ValueError(f"semantic comparison requires a source file below root: {path}")
    return resolved, relative


def _revision_now(revision: str, revision_getter: Callable[[], str] | None) -> str:
    if not isinstance(revision, str) or not revision:
        raise ValueError("semantic comparison revision must be a non-empty string")
    if revision_getter is None:
        return revision
    current = revision_getter()
    if not isinstance(current, str) or not current:
        raise ValueError("semantic comparison revision getter returned an empty revision")
    if current != revision:
        raise SemanticComparisonStaleError(f"workspace revision changed: {revision} -> {current}")
    return current


def _provider_evidence(registry: SemanticAdmissionRegistry, language: str) -> dict[str, tuple[str, ...]]:
    evidence: dict[str, tuple[str, ...]] = {}
    for identity in registry.cache_identity("parse", language=language):
        evidence[identity["provider_id"]] = tuple(identity.get("admission_evidence") or ())
    return evidence


def _symbol_claim(
    symbol: Any,
    *,
    provider_id: str,
    fingerprint: str | None,
    revision: str,
    relative: str,
    source_digest: str,
    evidence: tuple[str, ...],
) -> SemanticClaim:
    qualified_name = str(symbol.qualified_name or symbol.name or "")
    subject_key = f"symbol:{relative}:{qualified_name}"
    return make_claim(
        subject_key=subject_key,
        capability="parse",
        provider_id=provider_id,
        provider_fingerprint=fingerprint,
        revision=revision,
        path=relative,
        source_digest=source_digest,
        trust=str(symbol.trust),
        value={
            "kind": "symbol",
            "name": symbol.name,
            "qualified_name": symbol.qualified_name,
            "symbol_kind": symbol.kind,
            "language": symbol.language,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "signature": symbol.signature,
        },
        evidence=evidence,
    )


def _relation_claim(
    relation: tuple[str, str, str, str, str | None],
    *,
    slot: int,
    provider_id: str,
    fingerprint: str | None,
    revision: str,
    relative: str,
    source_digest: str,
    evidence: tuple[str, ...],
) -> SemanticClaim:
    source_id, target, kind, trust, relation_evidence = relation
    merged_evidence = evidence + ((str(relation_evidence),) if relation_evidence else ())
    return make_claim(
        subject_key=f"relation:{relative}:{source_id}:{slot}",
        capability="parse",
        provider_id=provider_id,
        provider_fingerprint=fingerprint,
        revision=revision,
        path=relative,
        source_digest=source_digest,
        trust=str(trust),
        value={
            "kind": "relation",
            "source": source_id,
            "target": target,
            "relation_kind": kind,
        },
        evidence=merged_evidence,
    )


def _diagnostic_claim(
    diagnostic: Any,
    *,
    slot: int,
    provider_id: str,
    fingerprint: str | None,
    revision: str,
    relative: str,
    source_digest: str,
    evidence: tuple[str, ...],
) -> SemanticClaim:
    return make_claim(
        subject_key=f"diagnostic:{relative}:{diagnostic.line}:{diagnostic.column}:{slot}",
        capability="parse",
        provider_id=provider_id,
        provider_fingerprint=fingerprint,
        revision=revision,
        path=relative,
        source_digest=source_digest,
        trust=str(diagnostic.trust),
        value={
            "kind": "diagnostic",
            "severity": diagnostic.severity,
            "message": diagnostic.message,
            "line": diagnostic.line,
            "column": diagnostic.column,
            "source": diagnostic.source,
        },
        evidence=evidence,
    )


def _claims_for_result(
    result: SemanticParseResult,
    *,
    provider_id: str,
    fingerprint: str | None,
    revision: str,
    relative: str,
    source_digest: str,
    evidence: tuple[str, ...],
) -> list[SemanticClaim]:
    claims: list[SemanticClaim] = []
    for symbol in sorted(
        result.symbols,
        key=lambda item: (item.qualified_name, item.kind, item.start_line, item.end_line, item.id),
    ):
        claims.append(_symbol_claim(
            symbol,
            provider_id=provider_id,
            fingerprint=fingerprint,
            revision=revision,
            relative=relative,
            source_digest=source_digest,
            evidence=evidence,
        ))

    relations = sorted(
        result.unresolved_relations,
        key=lambda item: tuple("" if value is None else str(value) for value in item),
    )
    for slot, relation in enumerate(relations):
        claims.append(_relation_claim(
            relation,
            slot=slot,
            provider_id=provider_id,
            fingerprint=fingerprint,
            revision=revision,
            relative=relative,
            source_digest=source_digest,
            evidence=evidence,
        ))

    diagnostics = sorted(
        result.diagnostics,
        key=lambda item: (
            -1 if item.line is None else item.line,
            -1 if item.column is None else item.column,
            item.severity,
            item.message,
            item.source,
            item.id,
        ),
    )
    for slot, diagnostic in enumerate(diagnostics):
        claims.append(_diagnostic_claim(
            diagnostic,
            slot=slot,
            provider_id=provider_id,
            fingerprint=fingerprint,
            revision=revision,
            relative=relative,
            source_digest=source_digest,
            evidence=evidence,
        ))
    return claims


def _bounded_empty_report(
    *,
    relative: str,
    language: str,
    revision: str,
    source_digest: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "path": relative,
        "language": language,
        "revision": revision,
        "source_digest": source_digest,
        "provider_ids": [],
        "providers": [],
        "provider_truncated": False,
        "claims": [],
        "claim_count": 0,
        "claim_truncated": False,
        "comparison_complete": False,
        "disagreements": [],
        "disagreement_count": 0,
        "truncated": False,
        "reason": reason,
    }


def compare_parse_providers(
    root: Path,
    path: Path,
    registry: SemanticAdmissionRegistry,
    revision: str,
    *,
    max_providers: int = DEFAULT_MAX_PROVIDERS,
    max_claims: int = DEFAULT_MAX_CLAIMS,
    max_disagreements: int = DEFAULT_MAX_DISAGREEMENTS,
    revision_getter: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if not isinstance(registry, SemanticAdmissionRegistry):
        raise TypeError("semantic comparison requires SemanticAdmissionRegistry")
    max_providers = _positive_int(max_providers, "max_providers")
    max_claims = _positive_int(max_claims, "max_claims")
    max_disagreements = _positive_int(max_disagreements, "max_disagreements")
    _revision_now(revision, revision_getter)

    source, relative = _resolve_source(root, path)
    language = detect_language(source)
    size = source.stat().st_size
    if size > MAX_PARSE_BYTES:
        return _bounded_empty_report(
            relative=relative,
            language=language,
            revision=revision,
            source_digest=sha256_file(source),
            reason=f"source exceeds semantic comparison parse bound: {size} > {MAX_PARSE_BYTES}",
        )

    raw = source.read_bytes()
    source_digest = sha256_bytes(raw)
    if language == "binary":
        return _bounded_empty_report(
            relative=relative,
            language=language,
            revision=revision,
            source_digest=source_digest,
            reason="binary source is not eligible for semantic parse comparison",
        )
    text = raw.decode("utf-8", errors="replace")
    file_id = stable_id("file", relative)

    all_providers = tuple(registry.providers_for("parse", language=language))
    selected = all_providers[:max_providers]
    provider_truncated = len(all_providers) > len(selected)
    admission_evidence = _provider_evidence(registry, language)

    claims_by_provider: dict[str, list[SemanticClaim]] = {}
    provider_statuses: list[dict[str, Any]] = []
    claim_count = 0
    claim_truncated = False
    all_complete = len(selected) >= 2 and not provider_truncated

    for provider in selected:
        provider_id = provider.id
        claims_by_provider[provider_id] = []
        try:
            fingerprint = provider.provider_fingerprint()
            if fingerprint is not None:
                fingerprint = str(fingerprint)
            result = provider.parse(Path(root).resolve(), source, text, file_id)
            if not isinstance(result, SemanticParseResult):
                raise TypeError("semantic provider parse must return SemanticParseResult")
            if result.provider != provider_id:
                raise ValueError(
                    f"semantic provider result identity mismatch: {provider_id} -> {result.provider}"
                )
            if not result.available:
                all_complete = False
                provider_statuses.append({
                    "provider_id": provider_id,
                    "status": "unavailable",
                    "reason": _bounded_reason(result.reason or "provider returned unavailable"),
                    "provider_fingerprint": fingerprint,
                    "claim_count": 0,
                })
                continue
            if getattr(result, "complete", True) is False:
                all_complete = False

            provider_claims = _claims_for_result(
                result,
                provider_id=provider_id,
                fingerprint=fingerprint,
                revision=revision,
                relative=relative,
                source_digest=source_digest,
                evidence=admission_evidence.get(provider_id, ()),
            )
            remaining = max_claims - claim_count
            if len(provider_claims) > remaining:
                provider_claims = provider_claims[:max(0, remaining)]
                claim_truncated = True
                all_complete = False
            claims_by_provider[provider_id].extend(provider_claims)
            claim_count += len(provider_claims)
            provider_statuses.append({
                "provider_id": provider_id,
                "status": "complete" if getattr(result, "complete", True) is not False else "incomplete",
                "reason": _bounded_reason(result.reason),
                "provider_fingerprint": fingerprint,
                "claim_count": len(provider_claims),
            })
            if claim_count >= max_claims:
                if provider is not selected[-1]:
                    claim_truncated = True
                    all_complete = False
                # Remaining providers are still executed to distinguish failure/unavailability from
                # negative evidence, but no additional claims are retained after the global bound.
        except Exception as exc:
            all_complete = False
            provider_statuses.append({
                "provider_id": provider_id,
                "status": "error",
                "reason": _bounded_reason(f"{type(exc).__name__}: {exc}"),
                "provider_fingerprint": None,
                "claim_count": 0,
            })

    comparison_complete = bool(all_complete and not claim_truncated)
    disagreement_result = compare_claims(
        claims_by_provider,
        comparison_complete=comparison_complete,
        max_disagreements=max_disagreements,
    )

    if sha256_file(source) != source_digest:
        raise SemanticComparisonStaleError(f"source digest changed during semantic comparison: {relative}")
    _revision_now(revision, revision_getter)

    claims = sorted(
        (claim for provider_claims in claims_by_provider.values() for claim in provider_claims),
        key=lambda claim: claim.id,
    )
    truncated = bool(provider_truncated or claim_truncated or disagreement_result["truncated"])
    return {
        "path": relative,
        "language": language,
        "revision": revision,
        "source_digest": source_digest,
        "provider_ids": [provider.id for provider in selected],
        "providers": provider_statuses,
        "provider_truncated": provider_truncated,
        "claims": claims,
        "claim_count": len(claims),
        "claim_truncated": claim_truncated,
        "comparison_complete": comparison_complete,
        "disagreements": disagreement_result["disagreements"],
        "disagreement_count": disagreement_result["count"],
        "truncated": truncated,
        "reason": "",
    }


__all__ = [
    "DEFAULT_MAX_CLAIMS",
    "DEFAULT_MAX_DISAGREEMENTS",
    "DEFAULT_MAX_PROVIDERS",
    "SemanticComparisonStaleError",
    "compare_parse_providers",
]

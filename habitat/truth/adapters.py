from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from .authority import AuthorityClass, legacy_authority
from .claims import TruthClaim, make_truth_claim


def _record(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    try:
        return dict(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("truth adapter requires a dataclass or mapping-like record") from exc


def _legacy_or_fail(trust: Any) -> AuthorityClass:
    authority = legacy_authority(trust if isinstance(trust, str) else None)
    if authority is None:
        raise ValueError(f"unknown legacy trust grade: {trust!r}")
    return authority


def _semantic_authority(trust: Any) -> AuthorityClass:
    """Clamp semantic-provider claims below canonical source authority."""

    if trust in {"exact", "semantic"}:
        return AuthorityClass.COMPILER_PRECISE
    if trust == "parser":
        return AuthorityClass.PARSER_DERIVED
    if trust in {"heuristic", "derived"}:
        return AuthorityClass.HEURISTIC_DERIVED
    raise ValueError(f"unknown semantic trust grade: {trust!r}")


def _json_value(raw: Any, *, field: str, expected: type | tuple[type, ...] | None = None) -> Any:
    if raw is None:
        value: Any = {} if expected is dict else [] if expected is list else None
    elif isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must contain valid JSON") from exc
    else:
        value = raw
    if expected is not None and not isinstance(value, expected):
        raise ValueError(f"{field} must decode to {getattr(expected, '__name__', expected)!s}")
    return value


def _optional_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("evidence confidence must be numeric or None")
    return float(value)


def claim_from_file_record(record: Any, *, revision: str) -> TruthClaim:
    row = _record(record)
    path = str(row["path"])
    digest = str(row["digest"])
    value = {
        "file_id": row["id"],
        "language": row["language"],
        "size": row["size"],
        "digest": digest,
        "mtime_ns": row["mtime_ns"],
        "indexed_bytes": row.get("indexed_bytes", 0),
        "index_truncated": bool(row.get("index_truncated", False)),
        "parse_complete": bool(row.get("parse_complete", True)),
    }
    return make_truth_claim(
        subject=f"file:{path}",
        predicate="source_snapshot",
        value=value,
        authority_class=AuthorityClass.SOURCE_EXACT,
        trust="exact",
        revision=revision,
        path=path,
        source_digest=digest,
        producer="workspace-index",
        provenance={"file_id": row["id"]},
    )


def claim_from_symbol_record(record: Any, *, revision: str, source_digest: str | None = None) -> TruthClaim:
    row = _record(record)
    trust = row.get("trust")
    authority = _legacy_or_fail(trust)
    value = {
        "symbol_id": row["id"],
        "file_id": row["file_id"],
        "name": row["name"],
        "qualified_name": row["qualified_name"],
        "kind": row["kind"],
        "language": row["language"],
        "start_line": row["start_line"],
        "end_line": row["end_line"],
        "signature": row.get("signature"),
        "summary": row.get("summary"),
    }
    return make_truth_claim(
        subject=f"symbol:{row['id']}",
        predicate="symbol",
        value=value,
        authority_class=authority,
        trust=trust,
        revision=revision,
        path=row.get("path"),
        source_digest=source_digest,
        producer="compiler",
        provenance={"record_id": row["id"], "file_id": row["file_id"]},
    )


def claim_from_relation_record(record: Any, *, revision: str) -> TruthClaim:
    row = _record(record)
    trust = row.get("trust")
    return make_truth_claim(
        subject=f"symbol:{row['source_id']}",
        predicate=f"relation:{row['kind']}",
        value={"target_id": row["target_id"], "evidence": row.get("evidence")},
        authority_class=_legacy_or_fail(trust),
        trust=trust,
        revision=revision,
        producer="compiler",
        provenance={
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "relation_kind": row["kind"],
        },
    )


def claim_from_diagnostic_record(
    record: Any,
    *,
    revision: str,
    source_digest: str | None = None,
) -> TruthClaim:
    row = _record(record)
    trust = row.get("trust")
    path = row.get("path")
    return make_truth_claim(
        subject=f"file:{path}" if path else f"diagnostic:{row['id']}",
        predicate=f"diagnostic:{row['severity']}",
        value={
            "diagnostic_id": row["id"],
            "message": row["message"],
            "line": row.get("line"),
            "column": row.get("column"),
            "source": row.get("source"),
        },
        authority_class=_legacy_or_fail(trust),
        trust=trust,
        revision=revision,
        path=path,
        source_digest=source_digest,
        producer=str(row.get("source") or "compiler"),
        provenance={"diagnostic_id": row["id"], "file_id": row.get("file_id")},
    )


def claim_from_occurrence_record(
    record: Any,
    *,
    revision: str,
    source_digest: str | None = None,
) -> TruthClaim:
    row = _record(record)
    trust = row.get("trust")
    path = row.get("path")
    occurrence_id = row["id"]
    subject_ref = row.get("target_id") or row.get("source_id") or occurrence_id
    return make_truth_claim(
        subject=f"symbol:{subject_ref}" if row.get("target_id") or row.get("source_id") else f"occurrence:{occurrence_id}",
        predicate=f"occurrence:{row['role']}",
        value={
            "occurrence_id": occurrence_id,
            "text": row["text"],
            "start_line": row["start_line"],
            "start_column": row.get("start_column"),
            "end_line": row.get("end_line"),
            "end_column": row.get("end_column"),
            "provider": row.get("provider"),
            "evidence": row.get("evidence"),
            "target_id": row.get("target_id"),
            "source_id": row.get("source_id"),
        },
        authority_class=_legacy_or_fail(trust),
        trust=trust,
        revision=revision,
        path=path,
        source_digest=source_digest,
        producer=str(row.get("provider") or "compiler"),
        provenance={"occurrence_id": occurrence_id, "file_id": row.get("file_id")},
    )


def claim_from_evidence_row(record: Any) -> TruthClaim:
    row = _record(record)
    trust = row.get("trust")
    data = _json_value(row.get("data_json"), field="data_json", expected=dict)
    confidence = _optional_confidence(data.get("confidence"))
    object_id = row.get("object_id")
    path = row.get("path")
    subject = f"object:{object_id}" if object_id else f"file:{path}" if path else f"evidence:{row['id']}"
    return make_truth_claim(
        subject=subject,
        predicate=f"evidence:{row['kind']}",
        value={
            "summary": row["summary"],
            "severity": row["severity"],
            "data": data,
            "active": bool(row.get("active", 1)),
        },
        authority_class=_legacy_or_fail(trust),
        trust=trust,
        confidence=confidence,
        revision=str(row["revision"]),
        path=path,
        source_digest=data.get("source_digest") if isinstance(data.get("source_digest"), str) else None,
        producer=str(row.get("source") or "evidence"),
        observed_at=row.get("created_at"),
        provenance={"evidence_id": row["id"]},
    )


def claim_from_semantic_claim(record: Any) -> TruthClaim:
    row = _record(record)
    trust = row.get("trust")
    evidence = row.get("evidence") or {}
    if not isinstance(evidence, Mapping):
        raise ValueError("semantic claim evidence must be a mapping")
    return make_truth_claim(
        subject=str(row["subject_key"]),
        predicate=f"semantic:{row['capability']}",
        value=row.get("value"),
        authority_class=_semantic_authority(trust),
        trust=trust,
        revision=str(row["revision"]),
        path=row.get("path"),
        source_digest=row.get("source_digest"),
        producer=str(row["provider_id"]),
        provider_fingerprint=row.get("provider_fingerprint"),
        provenance={
            "semantic_claim_id": row["id"],
            "provider_id": row["provider_id"],
            "evidence": dict(evidence),
        },
    )


def claim_from_epistemic_item(record: Any) -> TruthClaim:
    row = _record(record)
    provenance = _json_value(row.get("provenance_json"), field="provenance_json", expected=dict)
    invalidation = _json_value(row.get("invalidation_json"), field="invalidation_json", expected=list)
    return make_truth_claim(
        subject=f"epistemic:{row['id']}",
        predicate=str(row["kind"]),
        value={
            "statement": row["statement"],
            "status": row["status"],
            "scope": row.get("scope"),
            "invalidation": invalidation,
        },
        authority_class=AuthorityClass.MODEL_INFERRED,
        confidence=_optional_confidence(row.get("confidence")),
        revision=str(row["base_revision"]),
        producer=f"agent:{row['agent_id']}" if row.get("agent_id") else "epistemic",
        observed_at=row.get("updated_at") or row.get("created_at"),
        provenance={
            "epistemic_item_id": row["id"],
            "episode_id": row.get("episode_id"),
            "recorded_provenance": provenance,
        },
    )


def claim_from_memory(record: Any) -> TruthClaim:
    row = _record(record)
    provenance = _json_value(row.get("provenance_json"), field="provenance_json", expected=dict)
    evidence = _json_value(row.get("evidence_json"), field="evidence_json", expected=list)
    return make_truth_claim(
        subject=f"memory:{row['id']}",
        predicate=str(row["kind"]),
        value={
            "statement": row["statement"],
            "status": row["status"],
            "scope": row.get("scope"),
            "evidence": evidence,
            "valid_until_revision": row.get("valid_until_revision"),
            "supersedes": row.get("supersedes"),
            "invalidated_by": row.get("invalidated_by"),
        },
        authority_class=AuthorityClass.MEMORY_RECALLED,
        confidence=_optional_confidence(row.get("confidence")),
        revision=str(row["base_revision"]),
        producer=f"memory:{row['agent_id']}" if row.get("agent_id") else "memory",
        observed_at=row.get("updated_at") or row.get("created_at"),
        origin_claim_id=provenance.get("origin_claim_id"),
        origin_authority_class=provenance.get("origin_authority_class"),
        provenance={
            "memory_id": row["id"],
            "episode_id": row.get("episode_id"),
            "recorded_provenance": provenance,
        },
    )


__all__ = [
    "claim_from_diagnostic_record",
    "claim_from_epistemic_item",
    "claim_from_evidence_row",
    "claim_from_file_record",
    "claim_from_memory",
    "claim_from_occurrence_record",
    "claim_from_relation_record",
    "claim_from_semantic_claim",
    "claim_from_symbol_record",
]

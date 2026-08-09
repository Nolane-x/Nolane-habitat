from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TrustGrade = Literal["exact", "semantic", "parser", "heuristic", "derived"]


@dataclass(frozen=True)
class SourceAnchor:
    path: str
    start_line: int
    end_line: int
    digest: str


@dataclass
class FileRecord:
    id: str
    path: str
    language: str
    size: int
    digest: str
    mtime_ns: int
    indexed_text: str = ""
    indexed_bytes: int = 0
    index_truncated: bool = False
    parse_complete: bool = True


@dataclass
class SymbolRecord:
    id: str
    file_id: str
    path: str
    name: str
    qualified_name: str
    kind: str
    language: str
    start_line: int
    end_line: int
    signature: str | None = None
    summary: str | None = None
    trust: TrustGrade = "parser"


@dataclass
class RelationRecord:
    source_id: str
    target_id: str
    kind: str
    trust: TrustGrade
    evidence: str | None = None


@dataclass
class DiagnosticRecord:
    id: str
    file_id: str
    path: str
    severity: str
    message: str
    line: int | None = None
    column: int | None = None
    source: str = "compiler"
    trust: TrustGrade = "parser"


@dataclass
class OccurrenceRecord:
    id: str
    file_id: str
    path: str
    role: str
    target_id: str | None
    source_id: str | None
    text: str
    start_line: int
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    provider: str = "compiler"
    trust: TrustGrade = "parser"
    evidence: str | None = None


@dataclass
class EventRecord:
    kind: str
    path: str | None
    observed_at: str
    revision_before: str | None = None
    revision_after: str | None = None
    old_digest: str | None = None
    new_digest: str | None = None
    source: str = "workspace"
    details: dict[str, Any] = field(default_factory=dict)
    seq: int | None = None


@dataclass
class Revision:
    id: str
    parent_id: str | None
    root_digest: str
    reason: str
    changed_paths: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class ContextObject:
    object_id: str
    object_type: str
    relevance: float
    reason: str
    path: str | None = None
    source_range: tuple[int, int] | None = None
    lane: str = "unknown"
    trust: str | None = None


@dataclass
class ContextSlice:
    task: str
    revision: str
    objects: list[ContextObject]
    unknowns: list[str]
    omitted_candidates: int
    budget: int
    task_class: str = "generic"
    handle: str | None = None
    lane_counts: dict[str, int] = field(default_factory=dict)
    trust_counts: dict[str, int] = field(default_factory=dict)
    decision_packet: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionReceipt:
    id: str
    capability: str
    argv: list[str]
    cwd: str
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    changed_paths: list[str] = field(default_factory=list)
    structured: dict[str, Any] | None = None
    backend_id: str | None = None
    execution_backend: str | None = None
    source_authority_id: str | None = None
    execution_provider_id: str | None = None
    stdout_total_bytes: int = 0
    stderr_total_bytes: int = 0
    environment_fingerprint: dict[str, Any] = field(default_factory=dict)
    redaction: dict[str, Any] = field(default_factory=dict)


@dataclass
class TransactionRecord:
    id: str
    base_revision: str
    status: str
    operations: list[dict[str, Any]]
    changed_paths: list[str] = field(default_factory=list)
    committed_revision: str | None = None
    preview: list[dict[str, Any]] = field(default_factory=list)
    semantic_diff: dict[str, Any] = field(default_factory=dict)
    owner_agent_id: str | None = None
    lease_resources: list[str] = field(default_factory=list)
    rebased_from_revision: str | None = None
    rebased_onto_revision: str | None = None


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(v) for v in value]
    return value

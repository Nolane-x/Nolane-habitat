from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..model import DiagnosticRecord, SymbolRecord


_VALID_TRUST = frozenset({"heuristic", "parser", "derived", "semantic", "exact"})
_VALID_LIFECYCLES = frozenset({"stateless", "workspace-scoped", "bounded-process"})


@dataclass(frozen=True)
class SemanticProviderDescriptor:
    id: str
    languages: frozenset[str]
    layer: str
    trust_ceiling: str
    capabilities: frozenset[str]
    lifecycle: str
    incremental: bool = False
    source_authority: bool = False
    mutation_authority: bool = False
    provenance_required: bool = True

    def __post_init__(self) -> None:
        if self.trust_ceiling not in _VALID_TRUST:
            raise ValueError(f"unknown trust ceiling: {self.trust_ceiling}")
        if self.lifecycle not in _VALID_LIFECYCLES:
            raise ValueError(f"unknown lifecycle: {self.lifecycle}")
        if self.source_authority:
            raise ValueError("semantic descriptor cannot set source_authority")
        if self.mutation_authority:
            raise ValueError("semantic descriptor cannot set mutation_authority")
        if not self.provenance_required:
            raise ValueError("semantic descriptor requires provenance")


@dataclass
class SemanticParseResult:
    provider: str
    available: bool
    symbols: list[SymbolRecord] = field(default_factory=list)
    unresolved_relations: list[tuple[str, str, str, str, str | None]] = field(default_factory=list)
    diagnostics: list[DiagnosticRecord] = field(default_factory=list)
    reason: str = ""


class SemanticProvider:
    id = "base"
    languages: frozenset[str] = frozenset()
    layer = "syntax"
    trust_ceiling = "parser"
    capabilities: frozenset[str] = frozenset({"parse"})
    lifecycle = "stateless"
    incremental = False
    source_authority = False
    mutation_authority = False
    provenance_required = True

    def descriptor(self) -> SemanticProviderDescriptor:
        return SemanticProviderDescriptor(
            id=self.id,
            languages=frozenset(self.languages),
            layer=self.layer,
            trust_ceiling=self.trust_ceiling,
            capabilities=frozenset(self.capabilities),
            lifecycle=self.lifecycle,
            incremental=bool(self.incremental),
            source_authority=bool(self.source_authority),
            mutation_authority=bool(self.mutation_authority),
            provenance_required=bool(self.provenance_required),
        )

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        raise NotImplementedError

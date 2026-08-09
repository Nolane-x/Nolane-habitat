from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..model import DiagnosticRecord, SymbolRecord


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

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        raise NotImplementedError

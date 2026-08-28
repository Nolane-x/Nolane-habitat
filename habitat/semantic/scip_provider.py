from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import SemanticParseResult, SemanticProvider
from .scip_index import ScipDocument, ScipIndexSnapshot, ScipLocation


class ScipSemanticProvider(SemanticProvider):
    """Read-only compiler-index semantics from one explicitly activated SCIP snapshot."""

    layer = "compiler-index"
    trust_ceiling = "semantic"
    capabilities = frozenset({"definition", "references", "document-symbols", "diagnostics"})
    lifecycle = "workspace-scoped"
    incremental = False
    source_authority = False
    mutation_authority = False
    provenance_required = True

    def __init__(
        self,
        snapshot: ScipIndexSnapshot,
        *,
        provider_id: str,
        activation_revision: str,
        source_digests: dict[str, str | None],
    ) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id must be a non-empty string")
        if not isinstance(activation_revision, str) or not activation_revision:
            raise ValueError("activation_revision must be a non-empty string")
        self.snapshot = snapshot
        self.id = provider_id.strip()
        self.activation_revision = activation_revision
        self.source_digests = dict(source_digests)
        self.languages = frozenset(document.language for document in snapshot.documents if document.language)

    def available(self) -> tuple[bool, str]:
        return True, "validated SCIP index snapshot is active"

    def provider_fingerprint(self) -> str:
        payload = {
            "provider_id": self.id,
            "index_digest": self.snapshot.index_digest,
            "protocol_version": self.snapshot.protocol_version,
            "tool": {
                "name": self.snapshot.tool.name,
                "version": self.snapshot.tool.version,
                "arguments": list(self.snapshot.tool.arguments),
            },
            "documents": sorted(document.path for document in self.snapshot.documents),
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        return SemanticParseResult(
            provider=self.id,
            available=False,
            reason="SCIP provider is query-oriented; per-file parse is not an admitted capability",
        )

    def definitions(self, symbol: str) -> dict[str, Any]:
        return self._symbol_envelope(symbol, self.snapshot.definitions_by_symbol.get(symbol, ()))

    def references(self, symbol: str) -> dict[str, Any]:
        return self._symbol_envelope(symbol, self.snapshot.references_by_symbol.get(symbol, ()))

    def document(self, path: str) -> dict[str, Any]:
        document = self._document(path)
        base = self._base_envelope()
        base.update(
            {
                "path": document.path,
                "language": document.language,
                "position_encoding": document.position_encoding,
                "source_digest": self.source_digests.get(document.path),
                "symbols": [
                    {
                        "symbol": item.symbol,
                        "documentation": list(item.documentation),
                        "kind": item.kind,
                        "display_name": item.display_name,
                        "enclosing_symbol": item.enclosing_symbol,
                    }
                    for item in document.symbols
                ],
                "occurrences": [
                    {
                        "symbol": item.symbol,
                        "roles": item.roles,
                        "location": self._location(item.location) if item.location is not None else None,
                    }
                    for item in document.occurrences
                ],
                "diagnostics": [
                    {
                        "severity": item.severity,
                        "code": item.code,
                        "message": item.message,
                        "source": item.source,
                        "location": self._location(item.location) if item.location is not None else None,
                    }
                    for item in document.diagnostics
                ],
            }
        )
        return base

    def _symbol_envelope(self, symbol: str, locations: tuple[ScipLocation, ...]) -> dict[str, Any]:
        if not isinstance(symbol, str):
            raise TypeError("SCIP symbol query must be a string")
        base = self._base_envelope()
        base.update(
            {
                "symbol": symbol,
                "locations": [self._location(location) for location in locations],
            }
        )
        return base

    def _base_envelope(self) -> dict[str, Any]:
        return {
            "provider_id": self.id,
            "provider_fingerprint": self.provider_fingerprint(),
            "index_digest": self.snapshot.index_digest,
            "project_root": self.snapshot.project_root,
            "protocol_version": self.snapshot.protocol_version,
            "tool": {
                "name": self.snapshot.tool.name,
                "version": self.snapshot.tool.version,
                "arguments": list(self.snapshot.tool.arguments),
            },
            "activation_revision": self.activation_revision,
            "trust": "semantic",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _location(self, location: ScipLocation) -> dict[str, Any]:
        return {
            "path": location.path,
            "start_line": location.start_line,
            "start_column": location.start_column,
            "end_line": location.end_line,
            "end_column": location.end_column,
            "symbol": location.symbol,
            "roles": location.roles,
            "source_digest": self.source_digests.get(location.path),
        }

    def _document(self, path: str) -> ScipDocument:
        for document in self.snapshot.documents:
            if document.path == path:
                return document
        raise KeyError(path)


__all__ = ["ScipSemanticProvider"]

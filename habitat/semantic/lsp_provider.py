from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import SemanticParseResult, SemanticProvider
from .lsp_transport import LspProcessSession


_PROTOCOL_TARGET = "3.18"
_CAPABILITY_FIELDS = {
    "definition": "definitionProvider",
    "references": "referencesProvider",
    "hover": "hoverProvider",
    "document-symbols": "documentSymbolProvider",
}


class LspSemanticProvider(SemanticProvider):
    """Read-only Habitat semantic provider backed by one initialized LSP session."""

    layer = "language-semantic-service"
    trust_ceiling = "semantic"
    lifecycle = "workspace-scoped"
    incremental = True
    source_authority = False
    mutation_authority = False
    provenance_required = True

    def __init__(self, session: LspProcessSession) -> None:
        self._session = session
        self.id = session.spec.provider_id
        self.languages = frozenset(session.spec.languages)
        negotiated = session.capabilities
        capabilities = {
            name for name, field in _CAPABILITY_FIELDS.items() if bool(negotiated.get(field))
        }
        # publishDiagnostics is a server notification rather than a request capability flag.
        # Once the session is initialized Habitat can admit that passive, read-only evidence lane;
        # individual notifications are still version/revision/digest checked by the runtime manager.
        capabilities.add("diagnostics")
        self.capabilities = frozenset(capabilities)

    def available(self) -> tuple[bool, str]:
        ready = self._session.state == "READY"
        return ready, (
            "LSP initialize/capability handshake completed"
            if ready
            else f"LSP session is {self._session.state}"
        )

    def provider_fingerprint(self) -> str:
        executable = self._session.spec.argv[0]
        resolved = shutil.which(executable)
        if resolved is None:
            candidate = Path(executable).expanduser()
            resolved = str(candidate.resolve()) if candidate.exists() else executable
        payload = {
            "protocol": _PROTOCOL_TARGET,
            "provider_id": self.id,
            "languages": sorted(self.languages),
            "argv": list(self._session.spec.argv),
            "executable": resolved,
            "capabilities": self._session.capabilities,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        ready, reason = self.available()
        return SemanticParseResult(
            provider=self.id,
            available=ready,
            reason=(
                "LSP provider is query-oriented; file parsing is not an admitted capability"
                if ready
                else reason
            ),
        )

    def definition(
        self,
        uri: str,
        position: dict,
        *,
        revision: str,
        source_digest: str,
        document_version: int,
    ) -> dict[str, Any]:
        return self._query(
            "definition",
            "textDocument/definition",
            {"textDocument": {"uri": uri}, "position": position},
            revision=revision,
            source_digest=source_digest,
            document_version=document_version,
        )

    def references(
        self,
        uri: str,
        position: dict,
        *,
        revision: str,
        source_digest: str,
        document_version: int,
    ) -> dict[str, Any]:
        return self._query(
            "references",
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": position,
                "context": {"includeDeclaration": True},
            },
            revision=revision,
            source_digest=source_digest,
            document_version=document_version,
        )

    def hover(
        self,
        uri: str,
        position: dict,
        *,
        revision: str,
        source_digest: str,
        document_version: int,
    ) -> dict[str, Any]:
        return self._query(
            "hover",
            "textDocument/hover",
            {"textDocument": {"uri": uri}, "position": position},
            revision=revision,
            source_digest=source_digest,
            document_version=document_version,
        )

    def document_symbols(
        self,
        uri: str,
        *,
        revision: str,
        source_digest: str,
        document_version: int,
    ) -> dict[str, Any]:
        return self._query(
            "document-symbols",
            "textDocument/documentSymbol",
            {"textDocument": {"uri": uri}},
            revision=revision,
            source_digest=source_digest,
            document_version=document_version,
        )

    def diagnostic_snapshot(
        self,
        diagnostics: list[dict],
        *,
        revision: str,
        source_digest: str,
        document_version: int,
    ) -> dict[str, Any]:
        """Normalize one already-received publishDiagnostics notification as Habitat evidence."""
        if not isinstance(diagnostics, list) or not all(isinstance(item, dict) for item in diagnostics):
            raise TypeError("diagnostics must be a list of objects")
        return self._envelope(
            "textDocument/publishDiagnostics",
            diagnostics,
            revision=revision,
            source_digest=source_digest,
            document_version=document_version,
        )

    def _query(
        self,
        capability: str,
        method: str,
        params: dict,
        *,
        revision: str,
        source_digest: str,
        document_version: int,
    ) -> dict[str, Any]:
        if capability not in self.capabilities:
            raise RuntimeError(f"LSP capability was not negotiated: {capability}")
        self._validate_provenance(revision, source_digest, document_version)
        result = self._session.request(method, params)
        return self._envelope(
            method,
            result,
            revision=revision,
            source_digest=source_digest,
            document_version=document_version,
        )

    def _envelope(
        self,
        method: str,
        result: Any,
        *,
        revision: str,
        source_digest: str,
        document_version: int,
    ) -> dict[str, Any]:
        self._validate_provenance(revision, source_digest, document_version)
        return {
            "provider_id": self.id,
            "method": method,
            "trust": "semantic",
            "revision": revision,
            "source_digest": source_digest,
            "document_version": document_version,
            "provider_fingerprint": self.provider_fingerprint(),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }

    @staticmethod
    def _validate_provenance(revision: str, source_digest: str, document_version: int) -> None:
        if not isinstance(revision, str) or not revision:
            raise ValueError("revision must be a non-empty string")
        if not isinstance(source_digest, str) or not source_digest:
            raise ValueError("source_digest must be a non-empty string")
        if not isinstance(document_version, int) or isinstance(document_version, bool) or document_version < 1:
            raise ValueError("document_version must be a positive integer")

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .admission import SemanticAdmissionRegistry
from .lsp_provider import LspSemanticProvider
from .lsp_transport import LspProcessSession, LspServerSpec


class LspStaleResultError(RuntimeError):
    """Raised when source truth changes while an LSP request is in flight."""


@dataclass(frozen=True)
class _DocumentState:
    path: Path
    uri: str
    language_id: str
    source_digest: str
    revision: str
    version: int


_LANGUAGE_IDS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
}


class LspRuntimeManager:
    """Own explicitly activated, workspace-scoped read-only LSP runtimes."""

    def __init__(
        self,
        root: Path,
        semantic_registry: SemanticAdmissionRegistry,
        revision_getter: Callable[[], str],
    ) -> None:
        self.root = Path(root).resolve()
        self.semantic_registry = semantic_registry
        self.revision_getter = revision_getter
        self._sessions: dict[str, LspProcessSession] = {}
        self._providers: dict[str, LspSemanticProvider] = {}
        self._documents: dict[tuple[str, Path], _DocumentState] = {}
        self._diagnostics: dict[tuple[str, Path], dict[str, Any]] = {}
        self._lock = threading.RLock()

    def activate(self, spec: LspServerSpec) -> dict[str, Any]:
        provider_id = spec.provider_id
        with self._lock:
            if provider_id in self._sessions:
                raise ValueError(f"LSP provider is already active: {provider_id}")

        session = LspProcessSession(spec, self.root)
        try:
            session.start()
            provider = LspSemanticProvider(session)
            if self.semantic_registry.is_registered(provider_id):
                descriptor = self.semantic_registry.rebind(provider)
            else:
                descriptor = self.semantic_registry.register(provider)
            probe = self.semantic_registry.probe(provider_id)
            if not probe.detected:
                raise RuntimeError(f"LSP provider probe failed: {provider_id}: {probe.reason}")
            fingerprint = provider.provider_fingerprint()
            evidence = (
                "lsp.initialize=ready",
                "lsp.initialized=sent",
                f"workspace_root={self.root}",
                f"provider_fingerprint={fingerprint}",
                "capabilities=" + ",".join(sorted(descriptor.capabilities)),
            )
            self.semantic_registry.admit(provider_id, evidence=evidence)
            with self._lock:
                self._sessions[provider_id] = session
                self._providers[provider_id] = provider
            return {
                "provider_id": provider_id,
                "state": session.state,
                "languages": sorted(descriptor.languages),
                "capabilities": sorted(descriptor.capabilities),
                "provider_fingerprint": fingerprint,
                "admitted": True,
            }
        except Exception:
            session.close()
            raise

    def query(
        self,
        provider_id: str,
        capability: str,
        path: Path,
        *,
        position: dict | None = None,
    ) -> object:
        session, provider = self._ready_provider(provider_id)
        if capability not in provider.capabilities or capability == "diagnostics":
            raise ValueError(f"LSP capability is not an admitted request for {provider_id}: {capability}")

        document = self._sync_document(provider_id, session, provider, path)
        if capability in {"definition", "references", "hover"}:
            if not isinstance(position, dict):
                raise ValueError(f"position is required for LSP capability: {capability}")
        elif position is not None:
            raise ValueError(f"position is not accepted for LSP capability: {capability}")

        kwargs = {
            "revision": document.revision,
            "source_digest": document.source_digest,
            "document_version": document.version,
        }
        if capability == "definition":
            result = provider.definition(document.uri, position or {}, **kwargs)
        elif capability == "references":
            result = provider.references(document.uri, position or {}, **kwargs)
        elif capability == "hover":
            result = provider.hover(document.uri, position or {}, **kwargs)
        elif capability == "document-symbols":
            result = provider.document_symbols(document.uri, **kwargs)
        else:
            raise ValueError(f"unsupported read-only LSP capability: {capability}")

        # Notifications preceding the response are now deterministically visible. Capture only
        # version/revision/digest-bound diagnostics, then independently re-check the request result.
        self._capture_diagnostics(provider_id, session, provider)
        self._assert_fresh(provider_id, document)
        return result

    def diagnostics(self, provider_id: str, path: Path) -> dict[str, Any] | None:
        """Return current passive diagnostics, or None when no fresh version-bound snapshot exists."""
        session, provider = self._ready_provider(provider_id)
        if "diagnostics" not in provider.capabilities:
            raise ValueError(f"LSP diagnostics lane is not admitted for {provider_id}")
        document = self._sync_document(provider_id, session, provider, path)
        self._capture_diagnostics(provider_id, session, provider)
        self._assert_fresh(provider_id, document)
        key = (provider_id, document.path)
        with self._lock:
            snapshot = self._diagnostics.get(key)
        if snapshot is None:
            return None
        if (
            snapshot.get("revision") != document.revision
            or snapshot.get("source_digest") != document.source_digest
            or snapshot.get("document_version") != document.version
        ):
            return None
        return snapshot

    def close_provider(self, provider_id: str) -> None:
        with self._lock:
            session = self._sessions.get(provider_id)
            if session is None:
                return
            documents = [
                state
                for (owner_id, _), state in self._documents.items()
                if owner_id == provider_id
            ]

        if session.state == "READY":
            for document in sorted(documents, key=lambda item: str(item.path)):
                try:
                    session.notify(
                        "textDocument/didClose",
                        {"textDocument": {"uri": document.uri}},
                    )
                except Exception:
                    break

        session.close()
        if self.semantic_registry.is_admitted(provider_id):
            self.semantic_registry.revoke(provider_id, "LSP runtime closed")
        with self._lock:
            self._sessions.pop(provider_id, None)
            self._providers.pop(provider_id, None)
            stale_keys = [key for key in self._documents if key[0] == provider_id]
            for key in stale_keys:
                self._documents.pop(key, None)
            diagnostic_keys = [key for key in self._diagnostics if key[0] == provider_id]
            for key in diagnostic_keys:
                self._diagnostics.pop(key, None)

    def close(self) -> None:
        with self._lock:
            provider_ids = sorted(self._sessions)
        for provider_id in provider_ids:
            self.close_provider(provider_id)

    def status(self) -> dict[str, Any]:
        with self._lock:
            provider_ids = sorted(self._sessions)
            providers: list[dict[str, Any]] = []
            for provider_id in provider_ids:
                session = self._sessions[provider_id]
                provider = self._providers[provider_id]
                runtime = session.status()
                runtime.update(
                    {
                        "provider_id": provider_id,
                        "admitted": self.semantic_registry.is_admitted(provider_id),
                        "languages": sorted(provider.languages),
                        "capabilities": sorted(provider.capabilities),
                        "provider_fingerprint": provider.provider_fingerprint(),
                        "documents": [
                            {
                                "path": str(state.path),
                                "uri": state.uri,
                                "version": state.version,
                                "revision": state.revision,
                                "source_digest": state.source_digest,
                                "has_current_diagnostics": (provider_id, state.path) in self._diagnostics,
                            }
                            for (owner_id, _), state in sorted(
                                self._documents.items(), key=lambda item: (item[0][0], str(item[0][1]))
                            )
                            if owner_id == provider_id
                        ],
                    }
                )
                providers.append(runtime)
        return {"root": str(self.root), "providers": providers}

    def _ready_provider(self, provider_id: str) -> tuple[LspProcessSession, LspSemanticProvider]:
        with self._lock:
            session = self._sessions.get(provider_id)
            provider = self._providers.get(provider_id)
        if session is None or provider is None:
            raise ValueError(f"LSP provider is not active: {provider_id}")
        if session.state != "READY":
            if self.semantic_registry.is_admitted(provider_id):
                self.semantic_registry.revoke(provider_id, f"LSP session is {session.state}")
            raise RuntimeError(f"LSP provider is not ready: {provider_id}: {session.state}")
        if not self.semantic_registry.is_admitted(provider_id):
            raise RuntimeError(f"LSP provider is not admitted: {provider_id}")
        return session, provider

    def _sync_document(
        self,
        provider_id: str,
        session: LspProcessSession,
        provider: LspSemanticProvider,
        path: Path,
    ) -> _DocumentState:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"LSP path escapes workspace root: {resolved}") from exc
        if not resolved.is_file():
            raise FileNotFoundError(resolved)

        raw = resolved.read_bytes()
        text = raw.decode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        revision = self._revision()
        key = (provider_id, resolved)

        with self._lock:
            previous = self._documents.get(key)
            if previous is None:
                state = _DocumentState(
                    path=resolved,
                    uri=resolved.as_uri(),
                    language_id=self._language_id(resolved, provider.languages),
                    source_digest=digest,
                    revision=revision,
                    version=1,
                )
                session.notify(
                    "textDocument/didOpen",
                    {
                        "textDocument": {
                            "uri": state.uri,
                            "languageId": state.language_id,
                            "version": state.version,
                            "text": text,
                        }
                    },
                )
            elif previous.source_digest != digest:
                self._diagnostics.pop(key, None)
                state = _DocumentState(
                    path=resolved,
                    uri=previous.uri,
                    language_id=previous.language_id,
                    source_digest=digest,
                    revision=revision,
                    version=previous.version + 1,
                )
                session.notify(
                    "textDocument/didChange",
                    {
                        "textDocument": {"uri": state.uri, "version": state.version},
                        "contentChanges": [{"text": text}],
                    },
                )
            else:
                if previous.revision != revision:
                    self._diagnostics.pop(key, None)
                state = _DocumentState(
                    path=resolved,
                    uri=previous.uri,
                    language_id=previous.language_id,
                    source_digest=previous.source_digest,
                    revision=revision,
                    version=previous.version,
                )
            self._documents[key] = state
            return state

    def _capture_diagnostics(
        self,
        provider_id: str,
        session: LspProcessSession,
        provider: LspSemanticProvider,
    ) -> None:
        notifications = session.drain_notifications("textDocument/publishDiagnostics")
        if not notifications:
            return
        with self._lock:
            by_uri = {
                state.uri: ((owner_id, path), state)
                for (owner_id, path), state in self._documents.items()
                if owner_id == provider_id
            }

        for notification in notifications:
            params = notification.get("params")
            if not isinstance(params, dict):
                continue
            uri = params.get("uri")
            version = params.get("version")
            diagnostics = params.get("diagnostics")
            if not isinstance(uri, str) or not uri:
                continue
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                # Wave 2 promotes only explicitly version-bound diagnostics to current truth.
                continue
            if not isinstance(diagnostics, list) or not all(isinstance(item, dict) for item in diagnostics):
                continue
            target = by_uri.get(uri)
            if target is None:
                continue
            key, document = target
            if version != document.version:
                continue
            try:
                current_raw = document.path.read_bytes()
            except OSError:
                continue
            current_digest = hashlib.sha256(current_raw).hexdigest()
            current_revision = self._revision()
            if current_digest != document.source_digest or current_revision != document.revision:
                continue
            snapshot = provider.diagnostic_snapshot(
                diagnostics,
                revision=document.revision,
                source_digest=document.source_digest,
                document_version=document.version,
            )
            with self._lock:
                if self._documents.get(key) == document:
                    self._diagnostics[key] = snapshot

    def _assert_fresh(self, provider_id: str, snapshot: _DocumentState) -> None:
        current_raw = snapshot.path.read_bytes()
        current_digest = hashlib.sha256(current_raw).hexdigest()
        current_revision = self._revision()
        with self._lock:
            tracked = self._documents.get((provider_id, snapshot.path))
        if (
            tracked is None
            or tracked.version != snapshot.version
            or tracked.source_digest != snapshot.source_digest
            or current_digest != snapshot.source_digest
            or current_revision != snapshot.revision
        ):
            raise LspStaleResultError(
                "LSP result is stale because source digest, workspace revision, or document version changed"
            )

    def _revision(self) -> str:
        value = self.revision_getter()
        if not isinstance(value, str) or not value:
            raise ValueError("workspace revision getter must return a non-empty string")
        return value

    @staticmethod
    def _language_id(path: Path, languages: frozenset[str]) -> str:
        candidate = _LANGUAGE_IDS.get(path.suffix.lower())
        if candidate in languages:
            return candidate
        if len(languages) == 1:
            return next(iter(languages))
        if candidate is not None:
            return candidate
        return path.suffix.lower().lstrip(".") or "plaintext"

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from . import _workspace_core as _core
from .mutation import TransactionConflict
from .semantic.admission import SemanticAdmissionRegistry
from .semantic.fabric import semantic_fabric_report
from .semantic.lsp_runtime import LspRuntimeManager
from .semantic.lsp_transport import LspServerSpec
from .semantic.runtime import build_default_semantic_registry


_active_semantic_registry: ContextVar[SemanticAdmissionRegistry | None] = ContextVar(
    "habitat_active_semantic_registry", default=None
)
_core_compile_file = _core.compile_file
_core_compile_cache_fingerprint = _core.compile_cache_fingerprint


def _admission_compile_file(root: Path, path: Path, *, semantic_registry=None):
    registry = semantic_registry if semantic_registry is not None else _active_semantic_registry.get()
    return _core_compile_file(root, path, semantic_registry=registry)


def _admission_cache_fingerprint(language: str) -> dict:
    fingerprint = dict(_core_compile_cache_fingerprint(language))
    registry = _active_semantic_registry.get()
    if registry is not None:
        fingerprint["semantic_admission"] = registry.cache_identity("parse", language=language)
    return fingerprint


# Migration seam: alpha.19 resolves file compilation and cache fingerprints through module globals.
# Bind those hooks once to context-local admission state instead of duplicating the 3,400-line core.
# This remains non-authoritative outside a public HabitatWorkspace semantic scope and can disappear
# when refresh/compilation is extracted into its own bounded service.
_core.compile_file = _admission_compile_file
_core.compile_cache_fingerprint = _admission_cache_fingerprint


class HabitatWorkspace(_core.HabitatWorkspace):
    """Public workspace facade with workspace-owned semantic admission authority."""

    def __init__(self, habitat_dir: Path):
        # Recovery may refresh during the core constructor, so admission authority must exist first.
        self.semantic_registry = build_default_semantic_registry()
        # A manager object is cheap and process-free, but keep even that lazy so ordinary workspaces
        # retain their previous lifecycle until an explicit LSP facade operation is requested.
        self._lsp_runtime_manager: LspRuntimeManager | None = None
        super().__init__(habitat_dir)

    @contextmanager
    def _semantic_scope(self):
        token = _active_semantic_registry.set(self.semantic_registry)
        try:
            yield
        finally:
            _active_semantic_registry.reset(token)

    def _compiler_state_fingerprint(self) -> str:
        with self._semantic_scope():
            return super()._compiler_state_fingerprint()

    def refresh(self, reason: str = "refresh") -> dict:
        with self._semantic_scope():
            return super().refresh(reason)

    def refresh_paths(self, paths: list[str], reason: str = "targeted-refresh") -> dict:
        with self._semantic_scope():
            return super().refresh_paths(paths, reason)

    def reconcile(self) -> dict:
        with self._semantic_scope():
            return super().reconcile()

    def counterfactual_evaluate(self, world_id: str) -> dict:
        with self._semantic_scope():
            return super().counterfactual_evaluate(world_id)

    def _lsp_manager(self) -> LspRuntimeManager:
        manager = self._lsp_runtime_manager
        if manager is None:
            manager = LspRuntimeManager(
                self.source_root,
                semantic_registry=self.semantic_registry,
                revision_getter=lambda: self.revision,
            )
            self._lsp_runtime_manager = manager
        return manager

    def lsp_activate(self, spec: LspServerSpec) -> dict:
        """Explicitly activate one workspace-scoped read-only LSP provider."""
        return self._lsp_manager().activate(spec)

    def lsp_status(self) -> dict:
        """Report workspace LSP runtime state without spawning a language server."""
        return self._lsp_manager().status()

    def lsp_query(
        self,
        provider_id: str,
        capability: str,
        path: Path,
        *,
        position: dict | None = None,
    ) -> object:
        """Query one admitted read-only LSP capability against current source truth."""
        return self._lsp_manager().query(
            provider_id,
            capability,
            path,
            position=position,
        )

    def close(self) -> None:
        # Language servers may still need the source materialization and admission registry while
        # sending didClose/shutdown. Close them before the core closes backend/store authority.
        manager = self._lsp_runtime_manager
        self._lsp_runtime_manager = None
        if manager is not None:
            manager.close()
        super().close()

    def stage_change(
        self,
        operations: list[dict],
        episode_id: str | None = None,
        agent_id: str | None = None,
        lease_ttl_s: float = 120.0,
        approval_id: str | None = None,
    ) -> dict:
        # Trust grade describes evidence quality, not authority. Parser/heuristic/derived symbols are
        # useful for navigation and recovery but cannot authorize source replacement. Exact and
        # semantic anchors preserve the alpha.19 mutation path while admitted syntax providers stay
        # non-authoritative by construction.
        for operation in operations if isinstance(operations, list) else ():
            if not isinstance(operation, dict) or operation.get("op") != "replace_symbol_source":
                continue
            symbol_id = operation.get("symbol_id")
            if not isinstance(symbol_id, str) or not symbol_id:
                continue
            symbol = self.store.symbol_by_id(symbol_id)
            if symbol is not None and symbol["trust"] not in {"exact", "semantic"}:
                raise TransactionConflict(
                    "semantic mutation requires an exact or semantic source anchor; "
                    f"{symbol['trust']} evidence is non-authoritative"
                )
        return super().stage_change(operations, episode_id, agent_id, lease_ttl_s, approval_id)

    def semantic_fabric(self) -> dict:
        return semantic_fabric_report(self.source_root, semantic_registry=self.semantic_registry)


# The preserved core has one self-reference for disposable child-workspace verification. Point it
# back at the public facade so child workspaces inherit the same admission boundary.
_core.HabitatWorkspace = HabitatWorkspace

__all__ = ["HabitatWorkspace"]

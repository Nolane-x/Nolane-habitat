from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from . import _workspace_core as _core
from .semantic.admission import SemanticAdmissionRegistry
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


# The preserved core has one self-reference for disposable child-workspace verification. Point it
# back at the public facade so child workspaces inherit the same admission boundary.
_core.HabitatWorkspace = HabitatWorkspace

__all__ = ["HabitatWorkspace"]

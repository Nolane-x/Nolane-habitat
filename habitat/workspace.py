from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from . import _workspace_core as _core
from .mutation import TransactionConflict
from .semantic.admission import SemanticAdmissionRegistry
from .semantic.comparison import SemanticComparisonStaleError, compare_parse_providers
from .semantic.fabric import semantic_fabric_report
from .semantic.lsp_runtime import LspRuntimeManager
from .semantic.lsp_transport import LspServerSpec
from .semantic.runtime import build_default_semantic_registry
from .semantic.scip_runtime import ScipIndexerSpec, ScipRuntimeManager
from .services import IndexService, QueryService, RuntimeService, TransactionService
from .truth import (
    claim_from_diagnostic_record,
    claim_from_evidence_row,
    claim_from_file_record,
    claim_from_occurrence_record,
    claim_from_relation_record,
    claim_from_semantic_claim,
    claim_from_symbol_record,
    legacy_authority,
    operation_allows_evidence,
    project_truth,
)
from .util import sha256_file


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
        # Runtime managers are process-free/state-free until explicitly used. Keep them lazy so
        # ordinary workspace create/open/index/refresh never discovers or admits external semantics.
        self._lsp_runtime_manager: LspRuntimeManager | None = None
        self._scip_runtime_manager: ScipRuntimeManager | None = None
        # Core-decomposition services are ownership seams only. Their constructors perform no work.
        self._index_service: IndexService | None = None
        self._query_service: QueryService | None = None
        self._transaction_service: TransactionService | None = None
        self._runtime_service: RuntimeService | None = None
        # Disagreement comparison is explicitly requested and never persisted in this wave. Keep
        # only one bounded summary for diagnostic Fabric projection; claims remain call-local.
        self._semantic_disagreement_state: dict | None = None
        super().__init__(habitat_dir)

    @contextmanager
    def _semantic_scope(self):
        token = _active_semantic_registry.set(self.semantic_registry)
        try:
            yield
        finally:
            _active_semantic_registry.reset(token)

    def _indexing(self) -> IndexService:
        service = self._index_service
        if service is None:
            service = IndexService(self)
            self._index_service = service
        return service

    def _queries(self) -> QueryService:
        service = self._query_service
        if service is None:
            service = QueryService(self)
            self._query_service = service
        return service

    def _transactions(self) -> TransactionService:
        service = self._transaction_service
        if service is None:
            service = TransactionService(self)
            self._transaction_service = service
        return service

    def _runtime_operations(self) -> RuntimeService:
        service = self._runtime_service
        if service is None:
            service = RuntimeService(self)
            self._runtime_service = service
        return service

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

    def _scip_manager(self) -> ScipRuntimeManager:
        manager = self._scip_runtime_manager
        if manager is None:
            manager = ScipRuntimeManager(
                self.source_root,
                semantic_registry=self.semantic_registry,
                revision_getter=lambda: self.revision,
            )
            self._scip_runtime_manager = manager
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

    def lsp_diagnostics(self, provider_id: str, path: Path) -> dict | None:
        """Return latest fresh passive diagnostics; None means no current version-bound snapshot."""
        return self._lsp_manager().diagnostics(provider_id, path)

    def scip_activate(self, index_path: Path, provider_id: str | None = None) -> dict:
        """Explicitly activate one bounded read-only SCIP index provider."""
        return self._scip_manager().activate(index_path, provider_id=provider_id)

    def scip_generate(self, spec: ScipIndexerSpec) -> dict:
        """Explicitly generate and activate one bounded read-only SCIP index."""
        return self._scip_manager().generate(spec)

    def scip_status(self) -> dict:
        """Report SCIP runtime state without discovering or parsing any index automatically."""
        return self._scip_manager().status()

    def scip_definitions(self, provider_id: str, symbol: str) -> dict:
        """Return fresh read-only SCIP definition evidence for one symbol."""
        return self._scip_manager().definitions(provider_id, symbol)

    def scip_references(self, provider_id: str, symbol: str) -> dict:
        """Return fresh read-only SCIP reference evidence for one symbol."""
        return self._scip_manager().references(provider_id, symbol)

    def scip_document(self, provider_id: str, path: Path) -> dict:
        """Return one fresh source-bound SCIP document projection."""
        return self._scip_manager().document(provider_id, path)

    def _semantic_comparison_source(self, path: Path) -> tuple[Path, str]:
        """Resolve one comparison path without performing refresh or semantic work."""
        root = self.source_root.resolve()
        raw = Path(path)
        resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"semantic comparison path escapes source root: {path}") from exc
        if not relative or relative == "." or not resolved.is_file():
            raise ValueError(f"semantic comparison requires a source file below root: {path}")
        return resolved, relative

    def semantic_disagreements(self, path: Path) -> dict:
        """Explicitly compare admitted parse providers against one indexed source snapshot."""
        # Read-only semantic queries must never refresh source implicitly: refresh/compile can execute
        # an admitted primary provider before this explicit comparison. Resolve containment first,
        # then fail closed if canonical source no longer matches the workspace's indexed digest.
        source, relative = self._semantic_comparison_source(path)
        indexed = self.store.file_by_path(relative)
        if indexed is None:
            raise SemanticComparisonStaleError(
                f"workspace has no indexed source snapshot for {relative}; explicit reconcile required"
            )
        indexed_digest = str(indexed["digest"])
        current_digest = sha256_file(source)
        if current_digest != indexed_digest:
            raise SemanticComparisonStaleError(
                f"source digest changed since workspace revision for {relative}; explicit reconcile required"
            )

        revision = self.revision
        report = compare_parse_providers(
            self.source_root,
            source,
            self.semantic_registry,
            revision,
            revision_getter=lambda: self.revision,
        )
        self._semantic_disagreement_state = {
            "path": report["path"],
            "revision": report["revision"],
            "source_digest": report["source_digest"],
            "provider_count": len(report["provider_ids"]),
            "claim_count": report["claim_count"],
            "disagreement_count": report["disagreement_count"],
            "comparison_complete": report["comparison_complete"],
            "truncated": report["truncated"],
        }
        return report

    def _truth_current_digests(self, file_rows: list[object]) -> dict[str, str | None]:
        """Read current source bytes without refreshing or mutating workspace state."""
        root = self.source_root.resolve()
        current: dict[str, str | None] = {}
        for row in file_rows:
            path = str(row["path"])
            raw = Path(path)
            if raw.is_absolute():
                current[path] = None
                continue
            resolved = (root / raw).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                current[path] = None
                continue
            current[path] = sha256_file(resolved) if resolved.is_file() else None
        return current

    def truth_projection(self, *, semantic_claims=(), max_claims: int = 500) -> dict:
        """Project bounded current/stale truth from already-resident workspace evidence.

        This read-only facade never refreshes source, starts semantic runtimes, reconciles provider
        admission, or performs semantic comparison. Semantic-plane claims enter only when explicitly
        supplied by the caller.
        """
        revision = self.revision
        file_rows = list(self.store.all_files())
        symbol_rows = list(self.store.all_symbols())
        indexed_digests = {str(row["path"]): str(row["digest"]) for row in file_rows}
        current_digests = self._truth_current_digests(file_rows)

        claims = [claim_from_file_record(row, revision=revision) for row in file_rows]
        claims.extend(
            claim_from_symbol_record(
                row,
                revision=revision,
                source_digest=indexed_digests.get(str(row["path"])),
            )
            for row in symbol_rows
        )

        relation_keys: set[tuple[object, ...]] = set()
        for symbol in symbol_rows:
            for row in self.store.relations_for(str(symbol["id"])):
                key = (
                    row["source_id"],
                    row["target_id"],
                    row["kind"],
                    row["trust"],
                    row["evidence"],
                )
                if key in relation_keys:
                    continue
                relation_keys.add(key)
                claims.append(claim_from_relation_record(row, revision=revision))

        for row in self.store.all_diagnostics():
            path = str(row["path"]) if row["path"] is not None else None
            claims.append(
                claim_from_diagnostic_record(
                    row,
                    revision=revision,
                    source_digest=indexed_digests.get(path) if path is not None else None,
                )
            )

        occurrence_ids: set[str] = set()
        for file_row in file_rows:
            path = str(file_row["path"])
            for row in self.store.occurrences_for_path(path):
                occurrence_id = str(row["id"])
                if occurrence_id in occurrence_ids:
                    continue
                occurrence_ids.add(occurrence_id)
                claims.append(
                    claim_from_occurrence_record(
                        row,
                        revision=revision,
                        source_digest=indexed_digests.get(path),
                    )
                )

        claims.extend(claim_from_evidence_row(row) for row in self.store.active_evidence(limit=500))
        claims.extend(claim_from_semantic_claim(row) for row in semantic_claims)

        projection = project_truth(
            claims,
            current_revision=revision,
            current_digests=current_digests,
            max_claims=max_claims,
        )
        return {"revision": revision, **projection}

    def close(self) -> None:
        # Semantic runtimes may still need source materialization and the admission registry while
        # closing/revoking. Close them before the core closes backend/store authority.
        self._semantic_disagreement_state = None

        scip_manager = self._scip_runtime_manager
        self._scip_runtime_manager = None
        if scip_manager is not None:
            scip_manager.close()

        lsp_manager = self._lsp_runtime_manager
        self._lsp_runtime_manager = None
        if lsp_manager is not None:
            lsp_manager.close()
        super().close()

    def stage_change(
        self,
        operations: list[dict],
        episode_id: str | None = None,
        agent_id: str | None = None,
        lease_ttl_s: float = 120.0,
        approval_id: str | None = None,
    ) -> dict:
        # Trust labels describe evidence provenance. Action authority is declared separately and
        # evaluated categorically: no confidence value, plurality, or remembered origin can promote
        # a weaker anchor into source mutation authority.
        for operation in operations if isinstance(operations, list) else ():
            if not isinstance(operation, dict) or operation.get("op") != "replace_symbol_source":
                continue
            symbol_id = operation.get("symbol_id")
            if not isinstance(symbol_id, str) or not symbol_id:
                continue
            symbol = self.store.symbol_by_id(symbol_id)
            if symbol is not None:
                authority = legacy_authority(symbol["trust"])
                if not operation_allows_evidence("replace_symbol_source", authority):
                    raise TransactionConflict(
                        "source mutation requires an exact source-authorized anchor; "
                        f"{symbol['trust']} evidence is read-only and non-authoritative"
                    )
        return super().stage_change(operations, episode_id, agent_id, lease_ttl_s, approval_id)

    def semantic_fabric(self) -> dict:
        scip_manager = self._scip_runtime_manager
        if scip_manager is not None:
            scip_manager.reconcile_admissions()
        lsp_manager = self._lsp_runtime_manager
        if lsp_manager is not None:
            lsp_manager.reconcile_admissions()

        report = semantic_fabric_report(self.source_root, semantic_registry=self.semantic_registry)

        # Registry cache identities intentionally contain admitted providers only. Preserve an
        # explicitly activated-but-revoked SCIP runtime in the diagnostic Fabric without restoring
        # admission: runtime status owns lifecycle truth, while the registry remains the sole source
        # of selectable/admitted truth.
        if scip_manager is not None:
            provider_ids = {provider["id"] for provider in report["providers"]}
            for status in scip_manager.status()["providers"]:
                if status["provider_id"] in provider_ids:
                    continue
                report["providers"].append(
                    {
                        "id": status["provider_id"],
                        "layer": "compiler-index",
                        "available": True,
                        "detected": True,
                        "precision": "semantic",
                        "capabilities": tuple(status["capabilities"]),
                        "reason": status["stale_reason"] or "SCIP runtime is not admitted",
                        "command": None,
                        "version": status["tool"]["version"] or None,
                        "admitted": False,
                        "trust_ceiling": "semantic",
                        "lifecycle": "workspace-scoped",
                        "languages": tuple(status["languages"]),
                        "incremental": False,
                        "index_digest": status["index_digest"],
                        "provider_fingerprint": status["provider_fingerprint"],
                        "tool": status["tool"],
                        "activation_revision": status["activation_revision"],
                        "stale": status["stale"],
                    }
                )
                provider_ids.add(status["provider_id"])

            detected_count = sum(1 for provider in report["providers"] if provider["detected"])
            admitted_count = sum(1 for provider in report["providers"] if provider["admitted"])
            report["available_count"] = detected_count
            report["detected_count"] = detected_count
            report["admitted_count"] = admitted_count

        if self._semantic_disagreement_state is not None:
            state = dict(self._semantic_disagreement_state)
            state["current_revision"] = self.revision
            state["stale"] = state["revision"] != self.revision
            report["semantic_disagreement_state"] = state

        return report


# The preserved core has one self-reference for disposable child-workspace verification. Point it
# back at the public facade so child workspaces inherit the same admission boundary.
_core.HabitatWorkspace = HabitatWorkspace

__all__ = ["HabitatWorkspace"]
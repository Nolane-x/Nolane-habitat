from __future__ import annotations

from typing import Any

from .. import _workspace_core as _core
from ..mutation import TransactionConflict
from ..truth import legacy_authority, operation_allows_evidence


# Capture the pre-decomposition implementation before habitat.workspace intentionally rebinds
# _core.HabitatWorkspace for disposable child-workspace compatibility.
_CoreHabitatWorkspace = _core.HabitatWorkspace


class TransactionService:
    """Workspace-owned mutation seam with categorical source-authority enforcement."""

    __slots__ = ("workspace",)

    def __init__(self, workspace: Any):
        self.workspace = workspace

    def change_plan(self, operations: list[dict]) -> dict:
        return _CoreHabitatWorkspace.change_plan(self.workspace, operations)

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
            symbol = self.workspace.store.symbol_by_id(symbol_id)
            if symbol is not None:
                authority = legacy_authority(symbol["trust"])
                if not operation_allows_evidence("replace_symbol_source", authority):
                    raise TransactionConflict(
                        "source mutation requires an exact source-authorized anchor; "
                        f"{symbol['trust']} evidence is read-only and non-authoritative"
                    )
        return _CoreHabitatWorkspace.stage_change(
            self.workspace,
            operations,
            episode_id,
            agent_id,
            lease_ttl_s,
            approval_id,
        )

    def stage_symbol_change(
        self,
        symbol_id: str,
        new_source: str,
        episode_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        return _CoreHabitatWorkspace.stage_symbol_change(
            self.workspace,
            symbol_id,
            new_source,
            episode_id,
            agent_id,
        )

    def stage_symbol_rename(
        self,
        symbol_id: str,
        new_name: str,
        episode_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        return _CoreHabitatWorkspace.stage_symbol_rename(
            self.workspace,
            symbol_id,
            new_name,
            episode_id,
            agent_id,
        )

    def commit_change(self, txid: str, agent_id: str | None = None) -> dict:
        return _CoreHabitatWorkspace.commit_change(self.workspace, txid, agent_id)

    def rollback_change(self, txid: str, agent_id: str | None = None) -> dict:
        return _CoreHabitatWorkspace.rollback_change(self.workspace, txid, agent_id)

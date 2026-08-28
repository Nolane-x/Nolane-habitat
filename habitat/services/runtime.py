from __future__ import annotations

from typing import Any

from .. import _workspace_core as _core


# Capture the pre-facade implementation before habitat.workspace intentionally rebinds
# _workspace_core.HabitatWorkspace for disposable child-workspace compatibility.
_CoreHabitatWorkspace = _core.HabitatWorkspace


class RuntimeService:
    """Workspace-owned runtime observation seam with side-effect-free construction."""

    __slots__ = ("workspace",)

    def __init__(self, workspace: Any):
        self.workspace = workspace

    def runtime_ingest(
        self,
        signal: str,
        records: list[dict],
        *,
        agent_id: str | None = None,
        episode_id: str | None = None,
    ) -> dict:
        return _CoreHabitatWorkspace.runtime_ingest(
            self.workspace,
            signal,
            records,
            agent_id=agent_id,
            episode_id=episode_id,
        )

    def runtime_timeline(
        self,
        *,
        trace_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 200,
    ) -> dict:
        return _CoreHabitatWorkspace.runtime_timeline(
            self.workspace,
            trace_id=trace_id,
            agent_id=agent_id,
            limit=limit,
        )

    def runtime_topology(
        self,
        *,
        agent_id: str | None = None,
        limit: int = 500,
    ) -> dict:
        return _CoreHabitatWorkspace.runtime_topology(
            self.workspace,
            agent_id=agent_id,
            limit=limit,
        )

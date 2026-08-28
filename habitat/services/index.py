from __future__ import annotations

from typing import Any

from .. import _workspace_core as _core


# Capture the pre-decomposition implementation before habitat.workspace intentionally rebinds
# _core.HabitatWorkspace so disposable child workspaces inherit the public facade boundary.
_CoreHabitatWorkspace = _core.HabitatWorkspace


class IndexService:
    """Workspace-owned indexing seam with explicit preserved-core delegation."""

    __slots__ = ("workspace",)

    def __init__(self, workspace: Any):
        self.workspace = workspace

    def refresh(self, reason: str = "refresh") -> dict:
        return _CoreHabitatWorkspace.refresh(self.workspace, reason)

    def refresh_paths(
        self,
        paths: list[str],
        reason: str = "targeted-refresh",
    ) -> dict:
        return _CoreHabitatWorkspace.refresh_paths(self.workspace, paths, reason)

    def reconcile(self) -> dict:
        return _CoreHabitatWorkspace.reconcile(self.workspace)

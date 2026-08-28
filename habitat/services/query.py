from __future__ import annotations

from typing import Any

from .. import _workspace_core as _core


# Capture the pre-decomposition implementation before habitat.workspace intentionally rebinds
# _core.HabitatWorkspace for disposable child-workspace compatibility.
_CoreHabitatWorkspace = _core.HabitatWorkspace


class QueryService:
    """Workspace-owned read/query seam with explicit preserved-core delegation."""

    __slots__ = ("workspace",)

    def __init__(self, workspace: Any):
        self.workspace = workspace

    def query(self, query: str, limit: int = 20) -> list[dict]:
        return _CoreHabitatWorkspace.query(self.workspace, query, limit)

    def inspect_snapshot(self, object_id: str, include_source: str = "none") -> dict:
        return _CoreHabitatWorkspace.inspect_snapshot(self.workspace, object_id, include_source)

    def inspect_many(
        self,
        object_ids: list[str],
        include_source: str = "none",
        max_objects: int = 50,
    ) -> dict:
        return _CoreHabitatWorkspace.inspect_many(
            self.workspace,
            object_ids,
            include_source,
            max_objects,
        )

    def references_snapshot(self, object_id: str, limit: int = 200) -> dict:
        return _CoreHabitatWorkspace.references_snapshot(self.workspace, object_id, limit)

    def read_source(self, path: str, start_line: int = 1, max_lines: int = 200) -> dict:
        return _CoreHabitatWorkspace.read_source(self.workspace, path, start_line, max_lines)

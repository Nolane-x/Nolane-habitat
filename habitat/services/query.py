from __future__ import annotations

from typing import Any


class QueryService:
    """Workspace-owned read/query seam with side-effect-free construction."""

    __slots__ = ("workspace",)

    def __init__(self, workspace: Any):
        self.workspace = workspace

from __future__ import annotations

from typing import Any


class IndexService:
    """Workspace-owned indexing seam.

    Construction is intentionally side-effect free. Routing is added in the next TDD task.
    """

    __slots__ = ("workspace",)

    def __init__(self, workspace: Any):
        self.workspace = workspace

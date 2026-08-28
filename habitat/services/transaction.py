from __future__ import annotations

from typing import Any


class TransactionService:
    """Workspace-owned mutation seam with side-effect-free construction."""

    __slots__ = ("workspace",)

    def __init__(self, workspace: Any):
        self.workspace = workspace

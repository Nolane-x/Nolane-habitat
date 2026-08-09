from __future__ import annotations

from contextvars import ContextVar
import tempfile
from pathlib import Path

from habitat.workspace import HabitatWorkspace


_ORIGINAL_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory
_ACTIVE_TEMPORARY_DIRECTORIES: ContextVar[tuple["WorkspaceTrackingTemporaryDirectory", ...]] = ContextVar(
    "active_workspace_temporary_directories",
    default=(),
)
_ORIGINAL_CREATE = HabitatWorkspace.create.__func__
_CLEANUP_INSTALLED = False


class WorkspaceTrackingTemporaryDirectory(_ORIGINAL_TEMPORARY_DIRECTORY):
    """Close workspaces created under this temporary directory before deletion."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._workspaces: list[HabitatWorkspace] = []
        self._active_token = None

    def __enter__(self):
        name = super().__enter__()
        self._active_token = _ACTIVE_TEMPORARY_DIRECTORIES.set(
            _ACTIVE_TEMPORARY_DIRECTORIES.get() + (self,)
        )
        return name

    def track(self, workspace: HabitatWorkspace) -> None:
        self._workspaces.append(workspace)

    def cleanup(self) -> None:
        while self._workspaces:
            try:
                self._workspaces.pop().close()
            except Exception:
                pass
        super().cleanup()

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            if self._active_token is not None:
                _ACTIVE_TEMPORARY_DIRECTORIES.reset(self._active_token)
                self._active_token = None


def _track_workspace(workspace: HabitatWorkspace, habitat_dir: str | Path) -> HabitatWorkspace:
    habitat_path = Path(habitat_dir).resolve()
    for directory in reversed(_ACTIVE_TEMPORARY_DIRECTORIES.get()):
        try:
            habitat_path.relative_to(Path(directory.name).resolve())
        except ValueError:
            continue
        directory.track(workspace)
        break
    return workspace


def install_workspace_cleanup() -> None:
    """Install cross-platform cleanup for test workspaces created inside tempdirs."""
    global _CLEANUP_INSTALLED
    if _CLEANUP_INSTALLED:
        return

    def create_and_track(cls, source, habitat_dir, *, backend="local", reset=False):
        workspace = _ORIGINAL_CREATE(cls, source, habitat_dir, backend=backend, reset=reset)
        return _track_workspace(workspace, habitat_dir)

    HabitatWorkspace.create = classmethod(create_and_track)
    tempfile.TemporaryDirectory = WorkspaceTrackingTemporaryDirectory
    _CLEANUP_INSTALLED = True


class WorkspaceTemporaryDirectory(WorkspaceTrackingTemporaryDirectory):
    """Temporary directory that closes tracked workspaces before cleanup."""

    def __enter__(self):
        super().__enter__()
        return self

    def __fspath__(self) -> str:
        return self.name

    def create_workspace(self, source_root: Path, workspace_root: Path) -> HabitatWorkspace:
        return HabitatWorkspace.create(source_root, workspace_root)

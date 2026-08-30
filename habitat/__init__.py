"""Nolane Habitat: agent-native project cognition workspace."""

from __future__ import annotations

from .runtime_lifecycle import runtime_service_status, shutdown_runtime_services

__all__ = ["HabitatWorkspace", "runtime_service_status", "shutdown_runtime_services"]
__version__ = "0.1.0-alpha.19"


def __getattr__(name: str):
    """Preserve package-root compatibility without eagerly loading the Workspace/UI stack.

    Importing a projection-only submodule such as ``habitat.observability`` must not pull the
    browser/frontend transport graph into the interpreter.  The historical
    ``from habitat import HabitatWorkspace`` API remains exact and resolves only when requested.
    """
    if name == "HabitatWorkspace":
        from .workspace import HabitatWorkspace

        globals()[name] = HabitatWorkspace
        return HabitatWorkspace
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

from __future__ import annotations

from collections.abc import Iterable

from .admission import SemanticAdmissionRegistry
from .base import SemanticProvider
from .typescript import TypeScriptCompilerProvider


def build_default_semantic_registry(
    *,
    providers: Iterable[SemanticProvider] | None = None,
) -> SemanticAdmissionRegistry:
    """Build the admitted semantic runtime for the current host.

    Packaged providers are always registered so their identity is explicit. A provider only becomes
    selectable after its host probe succeeds and the runtime records concrete admission evidence.
    Missing providers remain registered but unadmitted, preserving fail-closed semantics.
    """
    registry = SemanticAdmissionRegistry()
    runtime_providers = tuple(providers) if providers is not None else (TypeScriptCompilerProvider(),)

    for provider in runtime_providers:
        descriptor = registry.register(provider)
        probe = registry.probe(descriptor.id)
        if not probe.detected:
            continue
        registry.admit(
            descriptor.id,
            evidence=(
                f"provider-contract:packaged:{descriptor.id}",
                f"host-probe:{probe.reason or 'detected'}",
            ),
        )

    return registry

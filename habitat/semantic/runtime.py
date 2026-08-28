from __future__ import annotations

from collections.abc import Iterable

from .admission import SemanticAdmissionRegistry
from .base import SemanticProvider
from .tree_sitter_provider import TreeSitterProvider
from .typescript import TypeScriptCompilerProvider


def build_default_semantic_registry(
    *,
    providers: Iterable[SemanticProvider] | None = None,
) -> SemanticAdmissionRegistry:
    """Build the admitted semantic runtime for the current host.

    Packaged providers are always registered so their identity is explicit. A provider only becomes
    selectable after its host probe succeeds and the runtime records concrete admission evidence.
    Missing providers remain registered but unadmitted, preserving fail-closed semantics.

    Registration order is semantic precedence. The TypeScript compiler API is attempted before the
    broader parser-trust Tree-sitter fallback for JavaScript/TypeScript.
    """
    registry = SemanticAdmissionRegistry()
    runtime_providers = (
        tuple(providers)
        if providers is not None
        else (TypeScriptCompilerProvider(), TreeSitterProvider())
    )

    for provider in runtime_providers:
        descriptor = registry.register(provider)
        probe = registry.probe(descriptor.id)
        if not probe.detected:
            continue
        fingerprint = provider.provider_fingerprint()
        evidence = [
            f"provider-contract:packaged:{descriptor.id}",
            f"host-probe:{probe.reason or 'detected'}",
        ]
        if fingerprint:
            evidence.append(f"runtime-fingerprint:{fingerprint}")
        registry.admit(descriptor.id, evidence=tuple(evidence))

    return registry

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .base import SemanticProvider, SemanticProviderDescriptor


@dataclass(frozen=True)
class SemanticProviderProbe:
    provider_id: str
    detected: bool
    reason: str


@dataclass(frozen=True)
class SemanticProviderAdmission:
    provider_id: str
    admitted: bool
    evidence: tuple[str, ...]


class SemanticAdmissionRegistry:
    """Gate semantic providers from host detection to Habitat admission.

    Registration establishes provider identity and descriptor validity. Probing records whether the
    provider is actually available on the current host. Admission is a separate, explicit decision
    that requires both a successful probe and concrete evidence. Capability selection only exposes
    providers that have crossed all three gates.
    """

    def __init__(self) -> None:
        self._providers: dict[str, SemanticProvider] = {}
        self._descriptors: dict[str, SemanticProviderDescriptor] = {}
        self._probes: dict[str, SemanticProviderProbe] = {}
        self._admissions: dict[str, SemanticProviderAdmission] = {}

    def register(self, provider: SemanticProvider) -> SemanticProviderDescriptor:
        descriptor = provider.descriptor()
        if descriptor.id in self._providers:
            raise ValueError(f"semantic provider already registered: {descriptor.id}")
        self._providers[descriptor.id] = provider
        self._descriptors[descriptor.id] = descriptor
        return descriptor

    def probe(self, provider_id: str) -> SemanticProviderProbe:
        provider = self._provider(provider_id)
        self._admissions.pop(provider_id, None)
        detected, reason = provider.available()
        result = SemanticProviderProbe(provider_id, bool(detected), str(reason or ""))
        self._probes[provider_id] = result
        return result

    def admit(self, provider_id: str, *, evidence: Iterable[str]) -> SemanticProviderAdmission:
        self._provider(provider_id)
        probe = self._probes.get(provider_id)
        if probe is None:
            raise ValueError(f"semantic provider must be probed before admission: {provider_id}")
        if not probe.detected:
            raise ValueError(f"semantic provider is not detected: {provider_id}")
        normalized = tuple(item.strip() for item in evidence if isinstance(item, str) and item.strip())
        if not normalized:
            raise ValueError(f"semantic provider admission requires evidence: {provider_id}")
        result = SemanticProviderAdmission(provider_id, True, normalized)
        self._admissions[provider_id] = result
        return result

    def providers_for(self, capability: str, *, language: str | None = None) -> tuple[SemanticProvider, ...]:
        selected: list[SemanticProvider] = []
        for provider_id, provider in self._providers.items():
            admission = self._admissions.get(provider_id)
            if admission is None or not admission.admitted:
                continue
            descriptor = self._descriptors[provider_id]
            if capability not in descriptor.capabilities:
                continue
            if language is not None and language not in descriptor.languages:
                continue
            selected.append(provider)
        return tuple(selected)

    def cache_identity(self, capability: str, *, language: str | None = None) -> list[dict]:
        """Return deterministic identity for admitted providers visible to one capability lane."""
        identities = []
        for provider_id, provider in self._providers.items():
            admission = self._admissions.get(provider_id)
            if admission is None or not admission.admitted:
                continue
            descriptor = self._descriptors[provider_id]
            if capability not in descriptor.capabilities:
                continue
            if language is not None and language not in descriptor.languages:
                continue
            probe = self._probes.get(provider_id)
            identities.append({
                "provider_id": descriptor.id,
                "languages": sorted(descriptor.languages),
                "layer": descriptor.layer,
                "trust_ceiling": descriptor.trust_ceiling,
                "capabilities": sorted(descriptor.capabilities),
                "lifecycle": descriptor.lifecycle,
                "incremental": bool(descriptor.incremental),
                "provider_fingerprint": provider.provider_fingerprint(),
                "probe_reason": probe.reason if probe is not None else "",
                "admission_evidence": list(admission.evidence),
            })
        identities.sort(key=lambda item: item["provider_id"])
        return identities

    def _provider(self, provider_id: str) -> SemanticProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ValueError(f"semantic provider is not registered: {provider_id}")
        return provider

from __future__ import annotations

import importlib
import importlib.util
import unittest
from pathlib import Path

from habitat.semantic.base import SemanticParseResult, SemanticProvider


class _AvailableProvider(SemanticProvider):
    id = "available-provider"
    languages = frozenset({"python"})
    layer = "syntax"
    trust_ceiling = "parser"
    capabilities = frozenset({"parse", "diagnostics"})
    lifecycle = "stateless"

    def __init__(self) -> None:
        self.fingerprint = "provider-v1"

    def available(self) -> tuple[bool, str]:
        return True, "probe succeeded"

    def provider_fingerprint(self) -> str | None:
        return self.fingerprint

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        return SemanticParseResult(self.id, True, reason="available")


class _UnavailableProvider(_AvailableProvider):
    id = "unavailable-provider"

    def available(self) -> tuple[bool, str]:
        return False, "runtime missing"


class _SecondProvider(_AvailableProvider):
    id = "second-provider"
    languages = frozenset({"typescript"})
    capabilities = frozenset({"parse"})


class SemanticAdmissionRegistryTests(unittest.TestCase):
    def admission_api(self):
        spec = importlib.util.find_spec("habitat.semantic.admission")
        self.assertIsNotNone(spec, "Semantic admission module must exist before providers can be admitted")
        return importlib.import_module("habitat.semantic.admission")

    def test_registry_rejects_duplicate_provider_identity(self):
        api = self.admission_api()
        registry = api.SemanticAdmissionRegistry()
        registry.register(_AvailableProvider())

        with self.assertRaises(ValueError):
            registry.register(_AvailableProvider())

    def test_admission_requires_successful_probe_and_nonempty_evidence(self):
        api = self.admission_api()
        registry = api.SemanticAdmissionRegistry()
        registry.register(_AvailableProvider())

        with self.assertRaises(ValueError):
            registry.admit("available-provider", evidence=("probe:test",))

        probe = registry.probe("available-provider")
        self.assertTrue(probe.detected)
        self.assertEqual("probe succeeded", probe.reason)

        with self.assertRaises(ValueError):
            registry.admit("available-provider", evidence=())

        admission = registry.admit(
            "available-provider",
            evidence=("probe:test", "contract:test-semantic-admission-registry"),
        )
        self.assertTrue(admission.admitted)
        self.assertEqual(
            ("probe:test", "contract:test-semantic-admission-registry"),
            admission.evidence,
        )

    def test_unavailable_provider_cannot_be_admitted(self):
        api = self.admission_api()
        registry = api.SemanticAdmissionRegistry()
        registry.register(_UnavailableProvider())

        probe = registry.probe("unavailable-provider")
        self.assertFalse(probe.detected)
        self.assertEqual("runtime missing", probe.reason)
        with self.assertRaises(ValueError):
            registry.admit("unavailable-provider", evidence=("probe:test",))

    def test_capability_selection_exposes_only_admitted_matching_providers(self):
        api = self.admission_api()
        registry = api.SemanticAdmissionRegistry()
        registry.register(_AvailableProvider())
        registry.register(_SecondProvider())
        registry.probe("available-provider")
        registry.probe("second-provider")
        registry.admit("available-provider", evidence=("probe:test",))

        python_parsers = registry.providers_for("parse", language="python")
        typescript_parsers = registry.providers_for("parse", language="typescript")
        diagnostics = registry.providers_for("diagnostics", language="python")

        self.assertEqual(("available-provider",), tuple(p.id for p in python_parsers))
        self.assertEqual((), tuple(p.id for p in typescript_parsers))
        self.assertEqual(("available-provider",), tuple(p.id for p in diagnostics))

    def test_reprobe_invalidates_prior_admission_until_fresh_evidence_readmits(self):
        api = self.admission_api()
        registry = api.SemanticAdmissionRegistry()
        registry.register(_AvailableProvider())
        registry.probe("available-provider")
        registry.admit("available-provider", evidence=("probe:first",))
        self.assertEqual(
            ("available-provider",),
            tuple(p.id for p in registry.providers_for("parse", language="python")),
        )

        registry.probe("available-provider")
        self.assertEqual((), registry.providers_for("parse", language="python"))

        registry.admit("available-provider", evidence=("probe:second",))
        self.assertEqual(
            ("available-provider",),
            tuple(p.id for p in registry.providers_for("parse", language="python")),
        )

    def test_cache_identity_tracks_provider_runtime_fingerprint(self):
        api = self.admission_api()
        registry = api.SemanticAdmissionRegistry()
        provider = _AvailableProvider()
        registry.register(provider)
        registry.probe(provider.id)
        registry.admit(provider.id, evidence=("probe:test",))

        first = registry.cache_identity("parse", language="python")
        self.assertEqual("provider-v1", first[0]["provider_fingerprint"])

        provider.fingerprint = "provider-v2"
        second = registry.cache_identity("parse", language="python")
        self.assertEqual("provider-v2", second[0]["provider_fingerprint"])
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from habitat.semantic.base import (
    SemanticParseResult,
    SemanticProvider,
    SemanticProviderDescriptor,
)
from habitat.semantic.fabric import semantic_fabric_report
from habitat.semantic.typescript import TypeScriptCompilerProvider


class _DummyProvider(SemanticProvider):
    id = "dummy-parser"
    languages = frozenset({"python"})
    layer = "syntax"
    trust_ceiling = "parser"
    capabilities = frozenset({"parse", "diagnostics"})
    lifecycle = "stateless"
    incremental = True

    def available(self) -> tuple[bool, str]:
        return True, "dummy available"

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        return SemanticParseResult(self.id, True, reason="dummy")


class SemanticFabricV2Tests(unittest.TestCase):
    def test_provider_descriptor_is_immutable_and_cannot_claim_source_or_mutation_authority(self):
        descriptor = _DummyProvider().descriptor()

        self.assertEqual("dummy-parser", descriptor.id)
        self.assertEqual(frozenset({"python"}), descriptor.languages)
        self.assertEqual("syntax", descriptor.layer)
        self.assertEqual("parser", descriptor.trust_ceiling)
        self.assertEqual(frozenset({"parse", "diagnostics"}), descriptor.capabilities)
        self.assertEqual("stateless", descriptor.lifecycle)
        self.assertTrue(descriptor.incremental)
        self.assertFalse(descriptor.source_authority)
        self.assertFalse(descriptor.mutation_authority)
        self.assertTrue(descriptor.provenance_required)
        with self.assertRaises(FrozenInstanceError):
            descriptor.id = "mutated"  # type: ignore[misc]

    def test_provider_descriptor_rejects_semantic_provider_authority_escalation(self):
        with self.assertRaises(ValueError):
            SemanticProviderDescriptor(
                id="unsafe",
                languages=frozenset({"python"}),
                layer="syntax",
                trust_ceiling="parser",
                capabilities=frozenset({"parse"}),
                lifecycle="stateless",
                source_authority=True,
            )
        with self.assertRaises(ValueError):
            SemanticProviderDescriptor(
                id="unsafe",
                languages=frozenset({"python"}),
                layer="syntax",
                trust_ceiling="parser",
                capabilities=frozenset({"parse"}),
                lifecycle="stateless",
                mutation_authority=True,
            )

    def test_existing_typescript_provider_gets_a_backward_compatible_contract(self):
        descriptor = TypeScriptCompilerProvider().descriptor()

        self.assertEqual("typescript-compiler-api", descriptor.id)
        self.assertEqual(frozenset({"javascript", "typescript"}), descriptor.languages)
        self.assertEqual("syntax", descriptor.layer)
        self.assertEqual("parser", descriptor.trust_ceiling)
        self.assertIn("parse", descriptor.capabilities)
        self.assertFalse(descriptor.source_authority)
        self.assertFalse(descriptor.mutation_authority)

    def test_discovery_fabric_preserves_wire_version_and_distinguishes_detected_from_admitted_providers(self):
        with tempfile.TemporaryDirectory() as td:
            report = semantic_fabric_report(Path(td))

        self.assertEqual(1, report["fabric_version"])
        self.assertEqual(2, report["contract_version"])
        self.assertEqual(report["available_count"], report["detected_count"])
        self.assertEqual(0, report["admitted_count"])
        self.assertTrue(report["providers"])
        for provider in report["providers"]:
            self.assertIn("detected", provider)
            self.assertIn("admitted", provider)
            self.assertIn("trust_ceiling", provider)
            self.assertIn("lifecycle", provider)
            # `available` is retained as the alpha.19 compatibility alias for host detection.
            self.assertEqual(provider["detected"], provider["available"])
            self.assertFalse(provider["admitted"])
        self.assertIn("does not mean admitted", report["claim_boundary"])

    def test_descriptor_rejects_unknown_trust_and_lifecycle_values(self):
        with self.assertRaises(ValueError):
            SemanticProviderDescriptor(
                id="bad-trust",
                languages=frozenset({"python"}),
                layer="syntax",
                trust_ceiling="unbounded",
                capabilities=frozenset({"parse"}),
                lifecycle="stateless",
            )
        with self.assertRaises(ValueError):
            SemanticProviderDescriptor(
                id="bad-life",
                languages=frozenset({"python"}),
                layer="syntax",
                trust_ceiling="parser",
                capabilities=frozenset({"parse"}),
                lifecycle="immortal-global",
            )


if __name__ == "__main__":
    unittest.main()

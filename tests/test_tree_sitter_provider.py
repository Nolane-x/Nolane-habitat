from __future__ import annotations

import importlib
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TreeSitterProviderContractTests(unittest.TestCase):
    def provider_api(self):
        spec = importlib.util.find_spec("habitat.semantic.tree_sitter_provider")
        self.assertIsNotNone(spec, "Semantic Fabric must provide a real Tree-sitter provider module")
        return importlib.import_module("habitat.semantic.tree_sitter_provider")

    def test_optional_extra_declares_tree_sitter_runtime_without_core_dependency(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        dependency_line = next(line for line in pyproject.splitlines() if line.startswith("dependencies ="))
        self.assertNotIn("tree-sitter", dependency_line)
        self.assertIn('tree-sitter = ["tree-sitter>=0.25,<0.26", "tree-sitter-language-pack>=1.12.3,<2"]', pyproject)

    def test_ci_exercises_real_tree_sitter_extra_on_every_matrix_lane(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn('.[dev,mcp,python-semantic,tree-sitter]', workflow)

    def test_provider_descriptor_is_parser_trust_and_non_authoritative(self):
        api = self.provider_api()
        provider = api.TreeSitterProvider()
        descriptor = provider.descriptor()

        self.assertEqual("tree-sitter", descriptor.id)
        self.assertEqual("syntax", descriptor.layer)
        self.assertEqual("parser", descriptor.trust_ceiling)
        self.assertIn("parse", descriptor.capabilities)
        self.assertIn("error-tolerant-parse", descriptor.capabilities)
        self.assertEqual("workspace-scoped", descriptor.lifecycle)
        self.assertFalse(descriptor.source_authority)
        self.assertFalse(descriptor.mutation_authority)
        self.assertTrue(descriptor.provenance_required)

    def test_real_runtime_advertises_only_grammars_it_can_load(self):
        api = self.provider_api()
        provider = api.TreeSitterProvider()
        detected, reason = provider.available()

        self.assertTrue(detected, reason)
        self.assertTrue({"python", "javascript", "typescript", "java"}.issubset(provider.languages))


if __name__ == "__main__":
    unittest.main()

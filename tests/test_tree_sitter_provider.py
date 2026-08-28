from __future__ import annotations

import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TreeSitterProviderContractTests(unittest.TestCase):
    def provider_api(self):
        spec = importlib.util.find_spec("habitat.semantic.tree_sitter_provider")
        self.assertIsNotNone(spec, "Semantic Fabric must provide a real Tree-sitter provider module")
        return importlib.import_module("habitat.semantic.tree_sitter_provider")

    def provider(self):
        provider = self.provider_api().TreeSitterProvider()
        detected, reason = provider.available()
        self.assertTrue(detected, reason)
        return provider

    def parse_source(self, suffix: str, text: str):
        provider = self.provider()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / f"sample{suffix}"
            path.write_text(text, encoding="utf-8")
            result = provider.parse(root, path, text, "file:test")
        self.assertTrue(result.available, result.reason)
        self.assertEqual("tree-sitter", result.provider)
        return result

    def test_optional_extra_declares_tree_sitter_runtime_without_core_dependency(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        dependency_line = next(line for line in pyproject.splitlines() if line.startswith("dependencies ="))
        self.assertNotIn("tree-sitter", dependency_line)
        self.assertIn('tree-sitter = ["tree-sitter>=0.26,<0.27", "tree-sitter-language-pack>=1.12.3,<2"]', pyproject)

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
        provider = self.provider()
        self.assertTrue({"python", "javascript", "typescript", "java"}.issubset(provider.languages))

    def test_extracts_python_declarations_with_parser_trust(self):
        result = self.parse_source(
            ".py",
            "class Greeter:\n    def hello(self):\n        return 'hi'\n\ndef top_level():\n    return 1\n",
        )
        by_name = {symbol.name: symbol for symbol in result.symbols}
        self.assertTrue({"Greeter", "hello", "top_level"}.issubset(by_name))
        self.assertTrue(all(by_name[name].trust == "parser" for name in ("Greeter", "hello", "top_level")))
        self.assertEqual("Greeter.hello", by_name["hello"].qualified_name)

    def test_extracts_javascript_typescript_and_java_declarations(self):
        cases = [
            (".js", "class Widget { render() { return 1; } }\nfunction greet() { return 1; }\n", {"Widget", "render", "greet"}),
            (".ts", "interface Shape { area(): number; }\nclass Circle { area(): number { return 1; } }\n", {"Shape", "Circle", "area"}),
            (".java", "class Greeter { int hello() { return 1; } }\n", {"Greeter", "hello"}),
        ]
        for suffix, text, expected in cases:
            with self.subTest(suffix=suffix):
                result = self.parse_source(suffix, text)
                names = {symbol.name for symbol in result.symbols}
                self.assertTrue(expected.issubset(names), (expected, names))
                self.assertTrue(all(symbol.trust == "parser" for symbol in result.symbols))

    def test_malformed_source_preserves_recoverable_symbols_and_emits_parser_diagnostic(self):
        result = self.parse_source(
            ".py",
            "def broken(:\n    pass\n\nclass Recovered:\n    def ok(self):\n        return 1\n",
        )
        self.assertIn("Recovered", {symbol.name for symbol in result.symbols})
        self.assertTrue(result.diagnostics)
        self.assertTrue(all(diag.provider == "tree-sitter" and diag.trust == "parser" for diag in result.diagnostics))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from habitat.compiler import compile_file
from habitat.semantic.runtime import build_default_semantic_registry


class TreeSitterCompileIntegrationTests(unittest.TestCase):
    def compile_source(self, name: str, text: str):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / name
            path.write_text(text, encoding="utf-8")
            registry = build_default_semantic_registry()
            compiled = compile_file(root, path, semantic_registry=registry)
        return compiled

    def test_valid_python_keeps_exact_ast_precedence(self):
        compiled = self.compile_source(
            "sample.py",
            "class Exact:\n    def ok(self):\n        return 1\n",
        )

        self.assertEqual("python-ast", compiled.provider)
        self.assertIn("Exact", {symbol.name for symbol in compiled.symbols})
        self.assertTrue(compiled.symbols)
        self.assertTrue(all(symbol.trust == "exact" for symbol in compiled.symbols))
        self.assertFalse(any(diag.source == "tree-sitter" for diag in compiled.diagnostics))

    def test_malformed_python_falls_back_to_admitted_tree_sitter_without_erasing_exact_diagnostic(self):
        compiled = self.compile_source(
            "broken.py",
            "def broken(:\n    pass\n\nclass Recovered:\n    def ok(self):\n        return 1\n",
        )

        self.assertEqual("tree-sitter", compiled.provider)
        self.assertIn("Recovered", {symbol.name for symbol in compiled.symbols})
        self.assertTrue(all(symbol.trust == "parser" for symbol in compiled.symbols))
        self.assertTrue(any(diag.source == "python-ast" and diag.trust == "exact" for diag in compiled.diagnostics))
        self.assertTrue(any(diag.source == "tree-sitter" and diag.trust == "parser" for diag in compiled.diagnostics))

    def test_java_uses_admitted_tree_sitter_before_regex_fallback(self):
        compiled = self.compile_source(
            "Greeter.java",
            "class Greeter { int hello() { return 1; } }\n",
        )

        self.assertEqual("tree-sitter", compiled.provider)
        self.assertTrue({"Greeter", "hello"}.issubset({symbol.name for symbol in compiled.symbols}))
        self.assertTrue(compiled.symbols)
        self.assertTrue(all(symbol.trust == "parser" for symbol in compiled.symbols))


if __name__ == "__main__":
    unittest.main()

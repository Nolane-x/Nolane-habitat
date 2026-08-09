import tempfile
import unittest
from pathlib import Path

from habitat.compiler import compile_file


class CompilerTests(unittest.TestCase):
    def test_python_ast_symbols_are_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root / "a.py"
            p.write_text('class A:\n    def run(self, value):\n        """do it"""\n        return helper(value)\n\ndef helper(x):\n    return x\n')
            cf = compile_file(root, p)
            names = {s.name: s for s in cf.symbols}
            self.assertEqual(names["A"].trust, "exact")
            self.assertEqual(names["run"].qualified_name, "A.run")
            self.assertEqual(names["run"].summary, "do it")

    def test_typescript_uses_best_available_parser_without_overclaiming(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root / "a.ts"
            p.write_text('export function login(x: string) { return x }')
            cf = compile_file(root, p)
            self.assertIn(cf.symbols[0].trust, {"parser", "heuristic"})
            if cf.provider == "typescript-compiler-api":
                self.assertEqual(cf.symbols[0].trust, "parser")

    def test_css_rule_symbols_are_unique_when_selectors_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root / "styles.css"
            p.write_text(".card { color: red; }\n.card { color: blue; }\n", encoding="utf-8")
            compiled = compile_file(root, p)
            self.assertEqual(len(compiled.symbols), 2)
            self.assertEqual(len({symbol.id for symbol in compiled.symbols}), 2)
            self.assertEqual([symbol.start_line for symbol in compiled.symbols], [1, 2])

if __name__ == "__main__": unittest.main()

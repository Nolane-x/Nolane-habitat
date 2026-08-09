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

if __name__ == "__main__": unittest.main()

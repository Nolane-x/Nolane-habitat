import os
import sys
import tempfile
import unittest
from importlib.util import cache_from_source
from pathlib import Path
from unittest.mock import patch

from habitat.execution import _prepare_python_bytecode_cache, run_action


class ExecutionTests(unittest.TestCase):
    def test_structured_receipt_and_change_readback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code = 'from pathlib import Path; print("hello"); Path("made.txt").write_text("x")'
            receipt = run_action(root, "fixture.run", [sys.executable, "-c", code])
            self.assertEqual(receipt.exit_code, 0)
            self.assertIn("hello", receipt.stdout)
            self.assertIn("made.txt", receipt.changed_paths)
            self.assertFalse(receipt.timed_out)

    def test_python_verify_uses_an_isolated_bytecode_cache_for_same_timestamp_edits(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "calc.py"
            test_root = root / "tests"
            test_root.mkdir()
            source.write_text("def add(a, b):\n    return a-b\n", encoding="utf-8")
            (test_root / "test_calc.py").write_text(
                "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                encoding="utf-8",
            )
            fixed_mtime = 1_700_000_000
            os.utime(source, (fixed_mtime, fixed_mtime))
            first = run_action(root, "python.pytest", [sys.executable, "-m", "pytest", "-q"], capability_kind="test")
            self.assertNotEqual(first.exit_code, 0)

            source.write_text("def add(a, b):\n    return a+b\n", encoding="utf-8")
            os.utime(source, (fixed_mtime, fixed_mtime))
            second = run_action(root, "python.pytest", [sys.executable, "-m", "pytest", "-q"], capability_kind="test")
            self.assertEqual(second.exit_code, 0, second.stdout + second.stderr)

    def test_python_bytecode_cache_invalidates_all_interpreter_tag_variants_for_project_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            source = root / "calc.py"
            source.write_text("value = 1\n", encoding="utf-8")
            cache_home = Path(td) / "cache-home"
            with patch("habitat.execution.tempfile.gettempdir", return_value=str(cache_home)):
                cache_root = _prepare_python_bytecode_cache(root)
                previous = sys.pycache_prefix
                sys.pycache_prefix = str(cache_root)
                try:
                    cache_path = Path(cache_from_source(str(source)))
                finally:
                    sys.pycache_prefix = previous
                alternate_tag = cache_path.with_name("calc.cpython-999.pyc")
                alternate_tag.parent.mkdir(parents=True, exist_ok=True)
                alternate_tag.write_bytes(b"stale")

                _prepare_python_bytecode_cache(root)

            self.assertFalse(alternate_tag.exists())

if __name__ == "__main__": unittest.main()

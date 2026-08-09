import sys
import tempfile
import unittest
from pathlib import Path

from habitat.execution import run_action


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

if __name__ == "__main__": unittest.main()

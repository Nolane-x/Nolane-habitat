import tempfile
import unittest
from pathlib import Path

from habitat.execution import discover_capabilities


class CapabilityTests(unittest.TestCase):
    def test_capabilities_expose_availability_instead_of_pretending(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "tests").mkdir()
            caps = discover_capabilities(root)
            self.assertTrue(caps)
            for cap in caps:
                self.assertIn("available", cap)
                self.assertIn("availability_reason", cap)
            unittest_cap = next(c for c in caps if c["id"] == "python.unittest")
            self.assertTrue(unittest_cap["available"])

if __name__ == "__main__": unittest.main()

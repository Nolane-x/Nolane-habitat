import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import unittest
from auth import login, validate_credentials


class AuthTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_credentials("alice@example.com", "secret"))
        self.assertEqual(login("alice@example.com", "secret"), "ok")

    def test_invalid(self):
        self.assertEqual(login("alice@example.com", "wrong"), "invalid")


if __name__ == "__main__":
    unittest.main()

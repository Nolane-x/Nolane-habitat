import unittest
from pathlib import Path

from habitat.toml_compat import tomllib


class TomlCompatibilityTests(unittest.TestCase):
    def test_runtime_toml_loader_parses_standard_toml(self):
        parsed = tomllib.loads('[project]\nname = "Nolane Habitat"\n')
        self.assertEqual(parsed["project"]["name"], "Nolane Habitat")

    def test_python_310_fallback_is_declared_as_a_runtime_dependency(self):
        config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("tomli>=2.0.1; python_version < '3.11'", config["project"]["dependencies"])


if __name__ == "__main__":
    unittest.main()

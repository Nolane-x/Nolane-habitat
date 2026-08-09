import json
import unittest
from pathlib import Path


class SchemaTests(unittest.TestCase):
    def test_all_json_schemas_are_valid_json(self):
        root = Path(__file__).parents[1] / "schemas"
        files = list(root.glob("*.schema.json"))
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            value = json.loads(path.read_text())
            self.assertEqual(value.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("$id", value)

if __name__ == "__main__": unittest.main()

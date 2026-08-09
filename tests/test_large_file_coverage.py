import tempfile
import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace
from habitat.compiler import MAX_INDEX_BYTES


class LargeFileCoverageTests(unittest.TestCase):
    def test_truncated_index_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / "p"; src.mkdir()
            (src / "notes.md").write_text("TOPIC habitat\n" + ("x" * (MAX_INDEX_BYTES + 1000)))
            ws = HabitatWorkspace.create(src, root / "h")
            row = ws.store.file_by_path("notes.md")
            self.assertEqual(row["index_truncated"], 1)
            entered = ws.enter()
            self.assertEqual(entered["index_health"]["truncated_text_files"], 1)
            ctx = ws.orient("habitat topic")
            self.assertTrue(any("truncated lexical indexes" in u for u in ctx.unknowns))

if __name__ == "__main__": unittest.main()

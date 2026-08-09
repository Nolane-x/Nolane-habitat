import sqlite3
import tempfile
import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace


class StorageTests(unittest.TestCase):
    def test_source_body_not_duplicated_in_files_table(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / "p"; src.mkdir()
            marker = "UNIQUE_SOURCE_MARKER_9f4b0a"
            (src / "big.py").write_text("# " + marker + "\n" + ("x = 1\n" * 1000))
            ws = HabitatWorkspace.create(src, root / "h")
            columns = [r[1] for r in ws.store.conn.execute("PRAGMA table_info(files)")]
            self.assertNotIn("indexed_text", columns)
            self.assertEqual(ws.store.get_meta("fts5"), "contentless")
            # Search still works even though FTS does not keep a retrievable content copy.
            self.assertTrue(ws.query(marker))

if __name__ == "__main__": unittest.main()

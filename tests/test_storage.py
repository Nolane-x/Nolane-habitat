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
            mode = ws.store.get_meta("fts5")
            self.assertIn(mode, {"contentless", "regular", "0"})
            # Newer SQLite builds use contentless FTS. Older builds fall back to a regular
            # FTS5 table; builds without FTS5 explicitly report that capability as unavailable.
            if mode != "0":
                self.assertTrue(ws.query(marker))

if __name__ == "__main__": unittest.main()

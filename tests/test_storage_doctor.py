import tempfile
import unittest
from pathlib import Path

from habitat.storage import SCHEMA_VERSION, Store


class StorageDoctorTests(unittest.TestCase):
    def test_healthy_workspace_reports_sqlite_and_schema_state(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / "habitat.sqlite3")
            try:
                report = store.doctor()
            finally:
                store.close()

        self.assertTrue(report["ok"])
        self.assertEqual(SCHEMA_VERSION, report["schema"]["expected_version"])
        self.assertEqual([], report["sqlite"]["foreign_key_violations"])
        self.assertEqual(["ok"], report["sqlite"]["integrity_check"])

    def test_foreign_key_corruption_is_reported_without_auto_repair(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / "habitat.sqlite3")
            try:
                store.conn.execute("PRAGMA foreign_keys = OFF")
                store.conn.execute(
                    """INSERT INTO symbols(
                        id,file_id,path,name,qualified_name,kind,language,start_line,end_line,trust
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("sym:orphan", "file:missing", "missing.py", "orphan", "orphan", "function", "python", 1, 1, "derived"),
                )
                store.conn.commit()
                store.conn.execute("PRAGMA foreign_keys = ON")
                report = store.doctor()
            finally:
                store.close()

        self.assertFalse(report["ok"])
        self.assertEqual("symbols", report["sqlite"]["foreign_key_violations"][0]["table"])

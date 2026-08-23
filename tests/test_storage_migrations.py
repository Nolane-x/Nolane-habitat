import sqlite3
import tempfile
import unittest
from pathlib import Path

from habitat.model import FileRecord
from habitat.storage import SCHEMA_VERSION, Store


class StorageMigrationTests(unittest.TestCase):
    def test_legacy_files_table_is_repaired_before_schema_version_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "legacy.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '1');
                CREATE TABLE files(
                  id TEXT PRIMARY KEY,
                  path TEXT UNIQUE NOT NULL,
                  language TEXT NOT NULL,
                  size INTEGER NOT NULL,
                  digest TEXT NOT NULL,
                  mtime_ns INTEGER NOT NULL
                );
                """
            )
            conn.close()

            store = Store(db_path)
            try:
                columns = {
                    row["name"]
                    for row in store.conn.execute("PRAGMA table_info(files)")
                }
                self.assertTrue(
                    {"indexed_bytes", "index_truncated", "parse_complete"} <= columns
                )
                self.assertEqual(str(SCHEMA_VERSION), store.get_meta("schema_version"))
                self.assertEqual(SCHEMA_VERSION, store.conn.execute("PRAGMA user_version").fetchone()[0])
                store.upsert_file(
                    FileRecord(
                        id="file:a.py",
                        path="a.py",
                        language="python",
                        size=1,
                        digest="digest",
                        mtime_ns=1,
                    )
                )
            finally:
                store.close()

    def test_malformed_schema_marker_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "malformed.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', 'unknown');
                """
            )
            conn.close()

            with self.assertRaisesRegex(RuntimeError, "invalid"):
                Store(db_path)

    def test_newer_workspace_is_rejected_before_schema_is_mutated(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "future.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                f"""
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '{SCHEMA_VERSION + 1}');
                """
            )
            conn.close()

            with self.assertRaisesRegex(RuntimeError, "newer"):
                Store(db_path)

            conn = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertEqual({"meta"}, tables)
            finally:
                conn.close()

    def test_legacy_workspace_is_backed_up_before_schema_repair(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "legacy.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '1');
                CREATE TABLE files(
                  id TEXT PRIMARY KEY,
                  path TEXT UNIQUE NOT NULL,
                  language TEXT NOT NULL,
                  size INTEGER NOT NULL,
                  digest TEXT NOT NULL,
                  mtime_ns INTEGER NOT NULL
                );
                """
            )
            conn.close()

            store = Store(db_path)
            store.close()

            backup = db_path.with_name("legacy.sqlite3.pre-migration-v1")
            self.assertTrue(backup.is_file())
            conn = sqlite3.connect(backup)
            try:
                columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(files)")
                }
            finally:
                conn.close()
            self.assertNotIn("indexed_bytes", columns)

    def test_unrepairable_legacy_table_does_not_receive_current_version_marker(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "broken.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '1');
                CREATE TABLE files(
                  id TEXT PRIMARY KEY,
                  path TEXT UNIQUE NOT NULL,
                  language TEXT NOT NULL,
                  size INTEGER NOT NULL,
                  mtime_ns INTEGER NOT NULL,
                  indexed_bytes INTEGER NOT NULL DEFAULT 0,
                  index_truncated INTEGER NOT NULL DEFAULT 0,
                  parse_complete INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            conn.close()

            with self.assertRaisesRegex(RuntimeError, "schema verification"):
                Store(db_path)

            conn = sqlite3.connect(db_path)
            try:
                version = conn.execute(
                    "SELECT value FROM meta WHERE key = 'schema_version'"
                ).fetchone()[0]
                self.assertEqual("1", version)
            finally:
                conn.close()

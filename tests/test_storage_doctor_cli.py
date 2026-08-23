import io
import json
import sqlite3
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from habitat.cli import main

if __package__:
    from .support import WorkspaceTemporaryDirectory
else:
    from support import WorkspaceTemporaryDirectory


class StorageDoctorCliTests(unittest.TestCase):
    def test_doctor_command_returns_database_health_without_refreshing(self):
        with WorkspaceTemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            workspace_root = root / "habitat"
            workspace = td.create_workspace(source, workspace_root)
            workspace.enter()
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["doctor", str(workspace_root)])

        self.assertEqual(0, exit_code)
        self.assertTrue(json.loads(output.getvalue())["ok"])

    def test_doctor_does_not_migrate_a_legacy_workspace_while_inspecting_it(self):
        with WorkspaceTemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            workspace_root = root / "habitat"
            workspace = td.create_workspace(source, workspace_root)
            workspace.enter()
            workspace.close()
            db_path = workspace_root / "habitat.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
            conn.close()

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["doctor", str(workspace_root)])

            conn = sqlite3.connect(db_path)
            try:
                version = conn.execute(
                    "SELECT value FROM meta WHERE key = 'schema_version'"
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(1, exit_code)
        self.assertEqual("1", version)
        self.assertFalse(json.loads(output.getvalue())["ok"])

import io
import json
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

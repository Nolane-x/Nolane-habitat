from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

from habitat.observatory import ObservatoryServer
from habitat.workspace import HabitatWorkspace


class ObservabilityCoreTests(unittest.TestCase):
    def make_ws(self):
        td = tempfile.TemporaryDirectory()
        base = Path(td.name)
        root = base / "project"
        root.mkdir()
        (root / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
        ws = HabitatWorkspace.create(root, base / "habitat")
        self.addCleanup(td.cleanup)
        self.addCleanup(ws.close)
        return ws

    def test_observatory_startup_and_health_are_state_neutral(self):
        ws = self.make_ws()
        database_before = "\n".join(ws.store.conn.iterdump())

        server = ObservatoryServer(ws).start(open_browser=False)
        try:
            self.assertTrue(server.status()["read_only"])
            with urllib.request.urlopen(server.url + "api/health", timeout=3) as response:
                health = json.loads(response.read())
            self.assertTrue(health["read_only"])
            self.assertEqual(health["revision"], ws.revision)
        finally:
            server.close()

        self.assertEqual(database_before, "\n".join(ws.store.conn.iterdump()))

    def test_observability_core_import_is_frontend_independent_and_projects_snapshot(self):
        repo_root = Path(__file__).parents[1]
        code = """
import json
import sys
from pathlib import Path
from habitat.observability import ObservatoryReadModel
from habitat.workspace import HabitatWorkspace

workspace = HabitatWorkspace(Path(sys.argv[1]))
try:
    snapshot = ObservatoryReadModel(workspace).snapshot()
    print(json.dumps({
        'frontend_loaded': 'habitat.observatory_frontend' in sys.modules,
        'legacy_observatory_loaded': 'habitat.observatory' in sys.modules,
        'read_only': snapshot['read_only'],
        'revision': snapshot['revision'],
    }))
finally:
    workspace.close()
"""
        ws = self.make_ws()
        result = subprocess.run(
            [sys.executable, "-c", code, str(ws.habitat_dir)],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["frontend_loaded"])
        self.assertFalse(report["legacy_observatory_loaded"])
        self.assertTrue(report["read_only"])
        self.assertEqual(report["revision"], ws.revision)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from habitat import server
from habitat.workspace import HabitatWorkspace


class ObservatoryHeadlessTests(unittest.TestCase):
    def make_workspace(self):
        td = tempfile.TemporaryDirectory()
        base = Path(td.name)
        source = base / "project"
        source.mkdir()
        (source / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
        ws = HabitatWorkspace.create(source, base / "habitat")
        self.addCleanup(td.cleanup)
        return ws

    def test_no_observatory_cli_never_calls_frontend_start(self):
        ws = self.make_workspace()
        habitat_dir = ws.habitat_dir
        ws.close()
        with patch.object(HabitatWorkspace, "observatory_start", side_effect=AssertionError("frontend start must stay disabled")):
            with patch.object(sys, "stdin", io.StringIO("")), patch.object(sys, "stderr", io.StringIO()):
                self.assertEqual(server.main([str(habitat_dir), "--no-observatory"]), 0)

    def test_headless_protocol_session_does_not_import_observatory_facade_or_frontend(self):
        ws = self.make_workspace()
        habitat_dir = ws.habitat_dir
        ws.close()
        repo_root = Path(__file__).parents[1]
        code = r'''import io
import json
import sys
from habitat.server import serve_stdio
from habitat.workspace import HabitatWorkspace
ws = HabitatWorkspace(__import__("pathlib").Path(sys.argv[1]))
try:
    inp = io.StringIO(json.dumps({"id":"headless","method":"workspace.enter","params":{}}) + "\n")
    out = io.StringIO()
    rc = serve_stdio(ws, inp, out)
    response = json.loads(out.getvalue())
    print(json.dumps({
        "rc": rc,
        "ok": response["ok"],
        "legacy_loaded": "habitat.observatory" in sys.modules,
        "frontend_loaded": "habitat.observatory_frontend" in sys.modules,
    }))
finally:
    ws.close()
'''
        result = subprocess.run(
            [sys.executable, "-c", code, str(habitat_dir)],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["rc"], 0)
        self.assertTrue(report["ok"])
        self.assertFalse(report["legacy_loaded"])
        self.assertFalse(report["frontend_loaded"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

from benchmarks.observatory_projection_costs import measure_observatory_costs
from habitat.observability import ObservatoryReadModel
from habitat.workspace import HabitatWorkspace


class ObservatoryProjectionFaultClosureTests(unittest.TestCase):
    def make_workspace(self):
        td = tempfile.TemporaryDirectory()
        base = Path(td.name)
        source = base / "project"
        source.mkdir()
        (source / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
        ws = HabitatWorkspace.create(source, base / "habitat")
        self.addCleanup(td.cleanup)
        self.addCleanup(ws.close)
        return ws

    @staticmethod
    def _http(url: str, *, method: str = "GET") -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=b"" if method not in {"GET", "HEAD"} else None, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5.0) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()

    def test_server_lifecycle_reads_and_rejected_mutations_leave_sqlite_unchanged(self):
        from habitat.observatory_frontend import ObservatoryServer

        ws = self.make_workspace()
        before = "\n".join(ws.store.conn.iterdump())
        server = ObservatoryServer(ws)
        try:
            server.start(open_browser=False)
            status = server.status()
            self.assertTrue(status["running"])
            self.assertTrue(status["read_only"])

            code, body = self._http(server.url + "api/health")
            self.assertEqual(code, 200)
            health = json.loads(body.decode("utf-8"))
            self.assertTrue(health["ok"])
            self.assertTrue(health["read_only"])
            self.assertEqual(health["revision"], ws.revision)

            # HEAD is authority-neutral whether the current compatibility surface answers it
            # explicitly (200) or BaseHTTPRequestHandler rejects it as unsupported (501).
            head_code, _ = self._http(server.url + "api/health", method="HEAD")
            self.assertIn(head_code, {200, 501})

            for method in ("POST", "PUT", "PATCH", "DELETE"):
                mutation_code, mutation_body = self._http(server.url + "api/health", method=method)
                self.assertEqual(mutation_code, 405, method)
                payload = json.loads(mutation_body.decode("utf-8"))
                self.assertEqual(payload["error"], "observer-read-only")
        finally:
            server.close()

        after = "\n".join(ws.store.conn.iterdump())
        self.assertEqual(before, after)

    def test_direct_projection_creates_no_shadow_database_and_clean_use_loads_no_frontend(self):
        ws = self.make_workspace()
        before_sqlite = sorted(p.name for p in ws.habitat_dir.glob("*.sqlite*"))
        snapshot = ObservatoryReadModel(ws).snapshot()
        after_sqlite = sorted(p.name for p in ws.habitat_dir.glob("*.sqlite*"))
        self.assertTrue(snapshot["read_only"])
        self.assertEqual(snapshot["revision"], ws.revision)
        self.assertEqual(before_sqlite, after_sqlite)

        habitat_dir = ws.habitat_dir
        ws.close()
        repo_root = Path(__file__).parents[1]
        code = r'''import json
import sys
from pathlib import Path
from habitat.workspace import HabitatWorkspace
from habitat.observability import ObservatoryReadModel
ws = HabitatWorkspace(Path(sys.argv[1]))
try:
    snap = ObservatoryReadModel(ws).snapshot()
    print(json.dumps({
        "read_only": snap["read_only"],
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
        self.assertTrue(report["read_only"])
        self.assertFalse(report["frontend_loaded"])

    def test_headless_protocol_read_never_starts_or_imports_frontend(self):
        ws = self.make_workspace()
        habitat_dir = ws.habitat_dir
        ws.close()
        repo_root = Path(__file__).parents[1]
        code = r'''import io
import json
import sys
from pathlib import Path
from habitat.server import serve_stdio
from habitat.workspace import HabitatWorkspace
ws = HabitatWorkspace(Path(sys.argv[1]))
try:
    inp = io.StringIO(json.dumps({"id":"closure","method":"workspace.enter","params":{}}) + "\n")
    out = io.StringIO()
    rc = serve_stdio(ws, inp, out)
    response = json.loads(out.getvalue())
    print(json.dumps({
        "rc": rc,
        "ok": response["ok"],
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
        self.assertFalse(report["frontend_loaded"])

    def test_legacy_facade_assets_endpoint_shapes_and_cost_claim_boundary_remain_compatible(self):
        import habitat.observatory as legacy
        from habitat.observatory_frontend import ObservatoryServer

        self.assertIs(legacy.ObservatoryServer, ObservatoryServer)
        self.assertIs(legacy.ObservatoryReadModel, ObservatoryReadModel)
        self.assertTrue(callable(legacy.start_observatory))

        package_root = resources.files("habitat")
        asset_root = package_root.joinpath("observatory_assets")
        for name in ("index.html", "app.js", "style.css"):
            self.assertTrue(asset_root.joinpath(name).is_file(), name)

        ws = self.make_workspace()
        server = legacy.start_observatory(ws, open_browser=False)
        try:
            health_code, health_body = self._http(server.url + "api/health")
            snapshot_code, snapshot_body = self._http(server.url + "api/snapshot")
            activity_code, activity_body = self._http(server.url + "api/activity?since=0")
        finally:
            server.close()

        self.assertEqual(health_code, 200)
        self.assertEqual(snapshot_code, 200)
        self.assertEqual(activity_code, 200)
        health = json.loads(health_body.decode("utf-8"))
        snapshot = json.loads(snapshot_body.decode("utf-8"))
        activity = json.loads(activity_body.decode("utf-8"))
        self.assertTrue({"ok", "read_only", "revision", "url"}.issubset(health))
        self.assertTrue({"read_only", "revision", "claim_boundary", "activity_seq"}.issubset(snapshot))
        self.assertTrue({"revision", "since_seq", "latest_seq", "events"}.issubset(activity))

        report = measure_observatory_costs(ws, include_frontend=False)
        self.assertIsNone(report["frontend_start_wall_ms"])
        self.assertIsNone(report["frontend_health_wall_ms"])
        claim = report["claim_boundary"].lower()
        self.assertIn("descriptive", claim)
        self.assertIn("no reasoning", claim)
        self.assertNotIn("improves reasoning", claim)
        self.assertNotIn("improves task", claim)


if __name__ == "__main__":
    unittest.main()

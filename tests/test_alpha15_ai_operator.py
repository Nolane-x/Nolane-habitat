import http.client
import json
import tempfile
import unittest
from pathlib import Path

from habitat.ui import BrowserRuntime
from habitat.workspace import HabitatWorkspace


@unittest.skipUnless(BrowserRuntime.probe().get("available"), "runtime browser unavailable")
class Alpha15AIOperatorRuntimeTests(unittest.TestCase):
    def _workspace(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        project = root / "project"
        project.mkdir()
        (project / "app.html").write_text(
            """<!doctype html><html><body><main><h1>Search</h1>
            <input id='query' aria-label='Search query'><input id='password' type='password' placeholder='Password'>
            <button id='go' onclick=\"document.querySelector('h1').textContent='Done'\">Go</button>
            </main></body></html>""",
            encoding="utf-8",
        )
        ws = HabitatWorkspace.create(project, root / "state")
        self.addCleanup(ws.close)
        self.addCleanup(td.cleanup)
        return ws

    def test_runtime_emits_authoritative_observer_frame_and_pointer_receipt(self):
        ws = self._workspace()
        opened = ws.open_ui_runtime("app.html")
        self.assertIsNone(opened["screenshot_path"])
        self.assertGreaterEqual(opened["observer_frame_seq"], 1)
        self.assertIn(opened["observer_stream"]["mode"], {"cdp-websocket-live", "cdp-screencast-cooperative", "snapshot-fallback"})
        frame = Path(opened["observer_frame_path"])
        self.assertTrue(frame.is_file())
        self.assertNotIn(":", frame.name)  # Windows-safe artifact naming despite colon-bearing semantic session IDs.
        self.assertEqual(frame.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

        query = next(e for e in opened["elements"] if e.get("attrs", {}).get("id") == "query")
        password = next(e for e in opened["elements"] if e.get("attrs", {}).get("id") == "password")
        preview = ws._runtime().preview_action(opened["session_id"], "fill", query["handle"], "habitat operator")
        self.assertEqual(preview["value_preview"], "habitat operator")
        self.assertFalse(preview["value_redacted"])
        self.assertGreater(preview["pointer"]["x"], 0)
        self.assertGreater(preview["pointer"]["y"], 0)

        secret = ws._runtime().preview_action(opened["session_id"], "fill", password["handle"], "dont-leak-this")
        self.assertEqual(secret["value_preview"], "[REDACTED]")
        self.assertTrue(secret["value_redacted"])
        self.assertIsNone(secret["value_length"])  # sensitive length is intentionally not exposed

        acted = ws.act_ui_runtime(opened["session_id"], "fill", query["handle"], "habitat operator")
        receipt = acted["action_receipt"]
        self.assertEqual(receipt["action"], "fill")
        self.assertEqual(receipt["handle"], query["handle"])
        self.assertEqual(receipt["value_preview"], "habitat operator")
        self.assertGreater(acted["observer_frame_seq"], opened["observer_frame_seq"])
        self.assertEqual(receipt["frame_seq"], acted["observer_frame_seq"])
        self.assertIn("changed", receipt["delta_counts"])

    def test_observatory_projects_ai_operator_and_serves_frame_read_only(self):
        ws = self._workspace()
        opened = ws.open_ui_runtime("app.html")
        password = next(e for e in opened["elements"] if e.get("attrs", {}).get("id") == "password")
        acted = ws.act_ui_runtime(opened["session_id"], "fill", password["handle"], "dont-leak-this")
        obs = ws.observatory_start(port=0, open_browser=False)
        self.addCleanup(ws.observatory_stop)

        conn = http.client.HTTPConnection("127.0.0.1", obs["port"], timeout=5)
        conn.request("GET", "/api/snapshot")
        response = conn.getresponse()
        snap = json.loads(response.read())
        conn.close()
        operator = snap["operator"]
        self.assertEqual(operator["session_id"], opened["session_id"])
        self.assertEqual(operator["status"], "live")
        self.assertEqual(operator["frame_seq"], acted["observer_frame_seq"])
        self.assertEqual(operator["last_action"]["value_preview"], "[REDACTED]")
        self.assertTrue(operator["last_action"]["value_redacted"])

        conn = http.client.HTTPConnection("127.0.0.1", obs["port"], timeout=5)
        conn.request("GET", f"/api/ui-frame?session_id={opened['session_id']}")
        response = conn.getresponse()
        data = response.read()
        headers = dict(response.getheaders())
        conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(headers.get("Content-Type"), "image/png")
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

        conn = http.client.HTTPConnection("127.0.0.1", obs["port"], timeout=5)
        conn.request("GET", "/")
        response = conn.getresponse()
        html = response.read().decode("utf-8")
        conn.close()
        self.assertIn("AI OPERATOR", html)
        self.assertIn('id="aiCursor"', html)
        self.assertIn('id="operatorFrame"', html)


class Alpha15OperatorAssetContractTests(unittest.TestCase):
    def test_operator_assets_keep_observer_only_claim_and_visual_controls(self):
        root = Path(__file__).resolve().parents[1] / "habitat" / "observatory_assets"
        html = (root / "index.html").read_text(encoding="utf-8")
        js = (root / "app.js").read_text(encoding="utf-8")
        css = (root / "style.css").read_text(encoding="utf-8")
        self.assertIn("OBSERVER ONLY · AI CONTROL PLANE", html)
        self.assertIn("PIXELS ARE OBSERVER MIRROR ONLY", html)
        self.assertIn("value_redacted", js)
        self.assertIn("queueOperatorStart", js)
        self.assertIn(".ai-cursor", css)
        self.assertIn(".target-box", css)

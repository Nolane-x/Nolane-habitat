import http.client
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from habitat.ui import BrowserRuntime
from habitat.ui.browser_provider import frame_key_for_session
from habitat.ui import browser_provider as browser_provider_module
from habitat.workspace import HabitatWorkspace


@unittest.skipUnless(BrowserRuntime.probe().get("available"), "runtime browser unavailable")
class Alpha16NearLiveForensicTests(unittest.TestCase):
    def _workspace(self, html=None):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        project = root / "project"
        project.mkdir()
        (project / "app.html").write_text(html or """<!doctype html><html><body>
          <input id='password' type='password' placeholder='Password'>
          <a id='reset' href='next.html?token=secret-link&safe=yes'>Reset</a>
          <button id='go' onclick="console.log('token=console-secret'); fetch('http://habitat.local/missing?api_key=network-secret&safe=yes').catch(()=>{}); document.body.dataset.done='1'">Go</button>
        </body></html>""", encoding="utf-8")
        ws = HabitatWorkspace.create(project, root / "state")
        self.addCleanup(td.cleanup)
        self.addCleanup(ws.close)
        return ws

    def test_cdp_stream_advances_and_observatory_can_poll_exact_frames(self):
        ws = self._workspace()
        opened = ws.open_ui_runtime("app.html")
        sid = opened["session_id"]
        self.assertEqual(opened["observer_stream"]["epoch"].split(":", 1)[0], "ui-stream")
        go = next(e for e in opened["elements"] if e.get("attrs", {}).get("id") == "go")
        acted = ws.act_ui_runtime(sid, "click", go["handle"])
        stream = acted["observer_stream"]
        self.assertIn(stream["mode"], {"cdp-websocket-live", "cdp-screencast-cooperative", "snapshot-fallback"})
        if stream["mode"].startswith("cdp-"):
            self.assertTrue(stream["active"])
            self.assertGreaterEqual(stream["seq"], 1)
            self.assertTrue(str(acted["observer_frame_source"]).startswith("cdp-"))

        obs = ws.observatory_start(port=0, open_browser=False)
        self.addCleanup(ws.observatory_stop)
        conn = http.client.HTTPConnection("127.0.0.1", obs["port"], timeout=5)
        conn.request("GET", f"/api/ui-stream?session_id={sid}")
        response = conn.getresponse(); meta = json.loads(response.read()); conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(meta["session_id"], sid)
        # Continuous CDP is allowed to advance after the action receipt was returned. The
        # read-model head must never go backwards, while the exact action-boundary frame remains
        # addressable inside the bounded frame ring.
        self.assertGreaterEqual(meta["frame_seq"], acted["observer_frame_seq"])
        self.assertEqual(meta["stream_epoch"], stream["epoch"])

        conn = http.client.HTTPConnection("127.0.0.1", obs["port"], timeout=5)
        conn.request("GET", f"/api/ui-frame?session_id={sid}&seq={acted['observer_frame_seq']}")
        response = conn.getresponse(); frame = response.read(); conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(frame[:8], b"\x89PNG\r\n\x1a\n")

    def test_websocket_cdp_continues_while_playwright_thread_is_idle(self):
        ws = self._workspace("""<!doctype html><html><body>
          <div id='pulse' style='width:40px;height:40px;background:#0ff'></div>
          <script>let n=0;setInterval(()=>{n++;document.getElementById('pulse').style.transform=`translateX(${n%180}px)`},16)</script>
        </body></html>""")
        opened = ws.open_ui_runtime("app.html")
        if opened["observer_stream"]["mode"] != "cdp-websocket-live":
            self.skipTest("continuous loopback CDP transport unavailable on this host")
        sid = opened["session_id"]
        key = frame_key_for_session(sid)
        meta_path = ws.habitat_dir / "artifacts" / "ui" / "live" / f"{key}-stream.json"
        before = json.loads(meta_path.read_text(encoding="utf-8"))
        # Deliberately make no Playwright call. A cooperative callback stream cannot advance here.
        time.sleep(0.55)
        after = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertGreater(after["stream_seq"], before["stream_seq"])
        self.assertEqual(after["stream_mode"], "cdp-websocket-live")
        self.assertEqual(after["frame_source"], "cdp-websocket-live")

    def test_sensitive_dom_console_network_and_href_are_redacted(self):
        ws = self._workspace()
        opened = ws.open_ui_runtime("app.html")
        password = next(e for e in opened["elements"] if e.get("attrs", {}).get("id") == "password")
        reset = next(e for e in opened["elements"] if e.get("attrs", {}).get("id") == "reset")
        self.assertNotIn("secret-link", reset.get("attrs", {}).get("href", ""))
        self.assertIn("%5BREDACTED%5D", reset.get("attrs", {}).get("href", ""))

        filled = ws.act_ui_runtime(opened["session_id"], "fill", password["handle"], "do-not-persist-me")
        pw = next(e for e in filled["elements"] if e.get("attrs", {}).get("id") == "password")
        self.assertEqual(pw["value"], "[REDACTED]")
        self.assertTrue(pw["value_redacted"])
        receipt = filled["action_receipt"]
        self.assertEqual(receipt["value_preview"], "[REDACTED]")
        self.assertIsNone(receipt["value_length"])
        self.assertNotIn("do-not-persist-me", json.dumps(filled, ensure_ascii=False))

        go = next(e for e in filled["elements"] if e.get("attrs", {}).get("id") == "go")
        acted = ws.act_ui_runtime(opened["session_id"], "click", go["handle"])
        payload = json.dumps(acted.get("events") or {}, ensure_ascii=False)
        self.assertNotIn("console-secret", payload)
        self.assertNotIn("network-secret", payload)
        self.assertIn("[REDACTED]", payload)

    def test_public_urls_and_json_console_assignments_are_scrubbed(self):
        ws = self._workspace("""<!doctype html><html><head><title>token=title-secret</title></head><body>
          <button id='go' onclick='console.log(JSON.stringify({token:"json-secret",safe:"ok"}))'>Go</button>
        </body></html>""")
        opened = ws.open_ui_runtime("app.html")
        self.assertNotIn("title-secret", opened.get("title", ""))
        go = next(e for e in opened["elements"] if e.get("attrs", {}).get("id") == "go")
        acted = ws.act_ui_runtime(opened["session_id"], "click", go["handle"])
        payload = json.dumps(acted, ensure_ascii=False)
        self.assertNotIn("json-secret", payload)
        self.assertIn("[REDACTED]", payload)

    def test_public_target_query_secret_is_not_exposed_or_persisted(self):
        ws = self._workspace()
        opened = ws.open_ui_runtime("app.html")
        rt = ws._runtime(); sess = rt._sessions[opened["session_id"]]
        # Simulate the internal target identity of a localhost navigation. The public read-model
        # must sanitize it before returning or persisting an activity record.
        sess.target = "http://127.0.0.1:43210/app.html?token=url-secret&safe=yes"
        observed = ws.observe_ui_runtime(opened["session_id"])
        public = json.dumps(observed, ensure_ascii=False)
        self.assertNotIn("url-secret", public)
        self.assertIn("REDACTED", public)

    def test_live_pixels_are_deleted_on_close_and_old_endpoint_goes_404(self):
        ws = self._workspace()
        opened = ws.open_ui_runtime("app.html")
        sid = opened["session_id"]
        frame = Path(opened["observer_frame_path"])
        self.assertTrue(frame.exists())
        live = frame.parent
        self.assertTrue(any(live.iterdir()))
        closed = ws.close_ui_runtime(sid)
        self.assertTrue(closed["ephemeral_frames_deleted"])
        self.assertFalse(frame.exists())
        self.assertFalse(any(live.glob(f"{frame_key_for_session(sid)}-*")))

        obs = ws.observatory_start(port=0, open_browser=False)
        self.addCleanup(ws.observatory_stop)
        conn = http.client.HTTPConnection("127.0.0.1", obs["port"], timeout=5)
        conn.request("GET", f"/api/ui-stream?session_id={sid}")
        response = conn.getresponse(); response.read(); conn.close()
        self.assertEqual(response.status, 404)

    def test_frame_key_is_collision_resistant_for_previously_colliding_session_names(self):
        self.assertNotEqual(frame_key_for_session("ui:a:b"), frame_key_for_session("ui:a_b"))
        self.assertRegex(frame_key_for_session("ui:a:b"), r"^[0-9a-f]{32}$")

    def test_frame_ring_is_bounded(self):
        ws = self._workspace()
        opened = ws.open_ui_runtime("app.html")
        rt = ws._runtime(); sess = rt._sessions[opened["session_id"]]
        rt._stop_screencast(sess)
        for _ in range(10):
            rt._capture_observer_frame(sess)
        key = frame_key_for_session(sess.id)
        frames = sorted((ws.habitat_dir / "artifacts" / "ui" / "live").glob(f"{key}-frame-*.png"))
        self.assertLessEqual(len(frames), 6)
        self.assertGreaterEqual(len(frames), 1)

    def test_project_page_cannot_reach_privileged_devtools_port(self):
        ws = self._workspace()
        opened = ws._runtime().open("app.html", allow_external=True)
        port = browser_provider_module._SHARED_DEBUG_PORT
        if port is None:
            self.skipTest("loopback DevTools endpoint unavailable on this host")
        sess = ws._runtime()._sessions[opened["session_id"]]
        result = sess.page.evaluate("""async port => {
          try { await fetch(`http://127.0.0.1:${port}/json/version`, {mode:'no-cors'}); return 'reachable'; }
          catch (e) { return 'blocked'; }
        }""", port)
        self.assertEqual(result, "blocked")
        self.assertEqual(opened["security"]["project_access_to_devtools"], "denied")

    def test_failed_open_does_not_leak_browser_context(self):
        ws = self._workspace()
        rt = ws._runtime(); rt._ensure_browser()
        before = len(rt._browser.contexts)
        with mock.patch.object(rt, "_set_project_content", side_effect=RuntimeError("synthetic load failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic load failure"):
                rt.open("app.html")
        self.assertEqual(len(rt._sessions), 0)
        self.assertEqual(len(rt._browser.contexts), before)

    def test_runtime_start_cleans_crash_left_ephemeral_frames_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); project = root / "project"; project.mkdir(); artifacts = root / "artifacts"; live = artifacts / "live"; live.mkdir(parents=True)
            (live / "orphan-frame.png").write_bytes(b"secret pixels")
            explicit = artifacts / "explicit.png"; explicit.write_bytes(b"keep")
            rt = BrowserRuntime(project, artifacts)
            self.assertFalse((live / "orphan-frame.png").exists())
            self.assertEqual(explicit.read_bytes(), b"keep")
            rt.close()


class Alpha16OperatorAssetForensicTests(unittest.TestCase):
    def test_app_js_is_text_only_and_has_session_epoch_invalidation(self):
        root = Path(__file__).resolve().parents[1] / "habitat" / "observatory_assets"
        raw = (root / "app.js").read_bytes()
        js = raw.decode("utf-8")
        html = (root / "index.html").read_text(encoding="utf-8")
        self.assertNotIn(b"\x00", raw)
        self.assertIn("adoptOperatorSession", js)
        self.assertIn("streamEpoch", js)
        self.assertIn("/api/ui-stream", js)
        self.assertIn("generation", js)
        self.assertIn("aria-selected", js)
        self.assertIn('id="operatorStream"', html)
        self.assertNotIn('<button', html.lower())
        self.assertNotIn('<input', html.lower())
        self.assertNotIn('<form', html.lower())

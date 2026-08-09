from __future__ import annotations

import socket
import tempfile
import threading
import unittest
from pathlib import Path

from habitat.observatory import ObservatoryReadModel, ObservatoryServer
from habitat.protocol import HabitatProtocol
from habitat.source_bridge import atomic_write
from habitat.ui.browser_provider import BrowserRuntime
from habitat.workspace import HabitatWorkspace


class Alpha17StabilityCompletionTests(unittest.TestCase):
    def make_ws(self, html: str | None = None, *, spaced: bool = False):
        td = tempfile.TemporaryDirectory()
        base = Path(td.name)
        project = base / ("project space" if spaced else "project")
        project.mkdir()
        (project / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        if html is not None:
            (project / "index.html").write_text(html, encoding="utf-8")
        ws = HabitatWorkspace.create(project, base / ("habitat space" if spaced else "habitat"))
        return td, project, ws

    def require_browser(self):
        probe = BrowserRuntime.probe()
        if not probe.get("available"):
            self.skipTest(probe.get("reason") or "browser unavailable")

    def test_operator_projection_survives_busy_non_ui_timeline(self):
        td, _, ws = self.make_ws()
        try:
            sid = "ui:projection:1"
            ws.activity_emit(
                "ui.runtime-opened", "ui", ref_id=sid, status="observing", summary="open",
                data={"session_id": sid, "target": "index.html", "url": "http://habitat.local/", "operator_frame_seq": 7,
                      "operator_stream_seq": 7, "operator_stream_epoch": "epoch-a", "operator_stream_mode": "cdp-websocket-live",
                      "operator_stream_active": True},
            )
            for i in range(120):
                ws.activity_emit("workspace.noise", "workspace", status="ok", summary=f"noise-{i}")
            operator = ObservatoryReadModel(ws).snapshot()["operator"]
            self.assertEqual(operator["session_id"], sid)
            self.assertEqual(operator["target"], "index.html")
            self.assertEqual(operator["frame_seq"], 7)
            self.assertTrue(operator["stream_active"])
        finally:
            ws.close(); td.cleanup()

    def test_operator_stream_epoch_resets_frame_monotonicity(self):
        td, _, ws = self.make_ws()
        try:
            sid = "ui:projection:2"
            ws.activity_emit("ui.runtime-opened", "ui", ref_id=sid, status="observing", summary="open",
                             data={"session_id": sid, "target": "index.html", "operator_frame_seq": 20,
                                   "operator_stream_seq": 20, "operator_stream_epoch": "epoch-old", "operator_stream_active": True})
            ws.activity_emit("ui.runtime-observed", "ui", ref_id=sid, status="observed", summary="new epoch",
                             data={"session_id": sid, "operator_frame_seq": 1, "operator_stream_seq": 1,
                                   "operator_stream_epoch": "epoch-new", "operator_stream_active": True})
            operator = ObservatoryReadModel(ws).snapshot()["operator"]
            self.assertEqual(operator["stream_epoch"], "epoch-new")
            self.assertEqual(operator["frame_seq"], 1)
            self.assertEqual(operator["stream_seq"], 1)
        finally:
            ws.close(); td.cleanup()

    def test_observatory_read_model_handles_space_paths(self):
        td, _, ws = self.make_ws(spaced=True)
        try:
            snap = ObservatoryReadModel(ws).snapshot()
            self.assertEqual(snap["revision"], ws.revision)
        finally:
            ws.close(); td.cleanup()

    def test_ipv6_loopback_url_is_bracketed_when_available(self):
        if not socket.has_ipv6:
            self.skipTest("IPv6 unavailable")
        td, _, ws = self.make_ws()
        obs = None
        try:
            try:
                obs = ObservatoryServer(ws, host="::1", port=0)
            except OSError as exc:
                self.skipTest(f"IPv6 loopback unavailable: {exc}")
            self.assertTrue(obs.url.startswith("http://[::1]:"), obs.url)
            obs.start(open_browser=False)
            self.assertTrue(obs.status()["running"])
        finally:
            if obs is not None:
                obs.close()
            ws.close(); td.cleanup()


    def test_atomic_write_uses_unique_same_directory_temps_under_concurrency(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.txt"
            path.write_bytes(b"seed")
            payloads = [f"writer-{i}".encode() for i in range(24)]
            barrier = threading.Barrier(len(payloads))
            errors = []

            def writer(data: bytes):
                try:
                    barrier.wait(timeout=3)
                    atomic_write(path, data)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(data,)) for data in payloads]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=5)
            self.assertFalse(errors, errors)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertIn(path.read_bytes(), payloads)
            self.assertFalse(list(path.parent.glob(f".{path.name}.habitat-*.tmp")))


    def test_ui_input_validation_fails_before_playwright_semantics(self):
        self.assertEqual(BrowserRuntime._normalize_viewport(None), {"width": 1440, "height": 900})
        with self.assertRaises(TypeError):
            BrowserRuntime._normalize_viewport("1440x900")
        with self.assertRaises(ValueError):
            BrowserRuntime._normalize_viewport({"width": True, "height": 900})
        with self.assertRaises(ValueError):
            BrowserRuntime._normalize_viewport({"width": 1440, "height": 900, "scale": 2})

        td, _, ws = self.make_ws("<!doctype html><html><body>ok</body></html>")
        try:
            proto = HabitatProtocol(ws)
            rsp = proto.handle({"id": "bad-vp", "method": "ui.runtime.open", "params": {"target": "index.html", "viewport": "wide"}})
            self.assertFalse(rsp["ok"])
            self.assertEqual(rsp["error"]["code"], "INVALID_PARAMS")
        finally:
            ws.close(); td.cleanup()

    def test_runtime_handles_are_unique_unspoofable_and_css_safe(self):
        self.require_browser()
        html = """<!doctype html><html><body>
        <button id='dup' onclick="document.querySelector('#out').textContent='first'">First</button>
        <button id='dup' onclick="document.querySelector('#out').textContent='second'">Second</button>
        <button id='other' data-nolane-habitat-handle='ui:id:dup'>Forged</button>
        <button id='a&quot;b' aria-label='token=supersecret'>Quoted</button>
        <div id='out'>none</div>
        </body></html>"""
        td, _, ws = self.make_ws(html)
        try:
            opened = ws.open_ui_runtime("index.html")
            sid = opened["session_id"]
            elements = opened["elements"]
            handles = [e["handle"] for e in elements]
            self.assertEqual(len(handles), len(set(handles)))
            self.assertIn("ui:id:dup", handles)
            second = next(e for e in elements if e.get("text") == "Second")
            self.assertNotEqual(second["handle"], "ui:id:dup")
            forged = next(e for e in elements if e.get("text") == "Forged")
            self.assertEqual(forged["handle"], "ui:id:other")
            quoted = next(e for e in elements if e.get("tag") == "button" and "%22" in e.get("handle", ""))
            self.assertNotIn("supersecret", str(quoted))
            self.assertIn("[REDACTED]", quoted.get("name") or "")
            result = ws.act_ui_runtime(sid, "click", second["handle"])
            out = next(e for e in result["elements"] if e["handle"] == "ui:id:out")
            self.assertEqual(out["text"], "second")
            preview = ws._runtime().preview_action(sid, "click", quoted["handle"])
            self.assertNotIn("supersecret", str(preview))
        finally:
            ws.close(); td.cleanup()

    def test_noisy_page_event_buffers_are_bounded_and_report_drops(self):
        self.require_browser()
        html = """<!doctype html><html><body>
        <button id='spam' onclick="for(let i=0;i<750;i++) console.log('event-'+i)">Spam</button>
        </body></html>"""
        td, _, ws = self.make_ws(html)
        try:
            opened = ws.open_ui_runtime("index.html")
            result = ws.act_ui_runtime(opened["session_id"], "click", "ui:id:spam")
            self.assertLessEqual(len(result["events"]["console"]), 100)
            self.assertGreaterEqual(result["events"]["dropped"]["console"], 200)
        finally:
            ws.close(); td.cleanup()

    def test_ui_assertion_supports_explicit_absence_and_rejects_invalid_counts(self):
        self.require_browser()
        td, _, ws = self.make_ws("<!doctype html><html><body><button id='present'>Here</button></body></html>")
        try:
            sid = ws.open_ui_runtime("index.html")["session_id"]
            result = ws.assert_ui_runtime(sid, [{"handle": "ui:id:missing", "exists": False}])
            self.assertTrue(result["passed"])
            with self.assertRaises(ValueError):
                ws.assert_ui_runtime(sid, [{"role": "button", "min_count": 2, "max_count": 1}])
            with self.assertRaises(TypeError):
                ws.assert_ui_runtime(sid, [{"role": "button", "exists": "no"}])
        finally:
            ws.close(); td.cleanup()


if __name__ == "__main__":
    unittest.main()

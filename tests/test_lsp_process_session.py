from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


FAKE_SERVER = Path(__file__).with_name("fake_lsp_server.py")


def fake_spec(mode: str = "normal"):
    from habitat.semantic.lsp_transport import LspServerSpec

    return LspServerSpec(
        provider_id="lsp.fake",
        languages=frozenset({"python"}),
        argv=(sys.executable, str(FAKE_SERVER), "--mode", mode),
        required_capabilities=frozenset({"definition"}),
    )


class LspProcessSessionTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="habitat-lsp-session-")
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_start_performs_initialize_and_enters_ready(self):
        from habitat.semantic.lsp_transport import LspProcessSession

        session = LspProcessSession(fake_spec(), self.root)
        try:
            capabilities = session.start()
            self.assertTrue(capabilities["definitionProvider"])
            status = session.status()
            self.assertEqual(status["state"], "READY")
            self.assertEqual(status["provider_id"], "lsp.fake")
            self.assertEqual(status["root"], str(self.root.resolve()))
            self.assertEqual(status["pending_requests"], 0)
        finally:
            session.close()
        self.assertEqual(session.status()["state"], "CLOSED")

    def test_request_round_trip_after_start(self):
        from habitat.semantic.lsp_transport import LspProcessSession

        session = LspProcessSession(fake_spec(), self.root)
        try:
            session.start()
            result = session.request("fake/state", {})
            self.assertIsInstance(result, dict)
            self.assertIn("pid", result)
        finally:
            session.close()

    def test_initialize_error_fails_closed(self):
        from habitat.semantic.lsp_transport import LspProcessSession

        session = LspProcessSession(fake_spec("initialize-error"), self.root)
        with self.assertRaises(RuntimeError):
            session.start()
        self.assertEqual(session.status()["state"], "FAILED")
        session.close()

    def test_required_capability_mismatch_fails_start(self):
        from habitat.semantic.lsp_transport import LspProcessSession

        session = LspProcessSession(fake_spec("unsupported-capability"), self.root)
        with self.assertRaises(RuntimeError):
            session.start()
        self.assertEqual(session.status()["state"], "FAILED")
        session.close()

    def test_close_is_idempotent(self):
        from habitat.semantic.lsp_transport import LspProcessSession

        session = LspProcessSession(fake_spec(), self.root)
        session.start()
        session.close()
        session.close()
        self.assertEqual(session.status()["state"], "CLOSED")


if __name__ == "__main__":
    unittest.main()

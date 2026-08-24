import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from habitat.protocol import MAX_REQUEST_BYTES, HabitatProtocol, ProtocolError, parse_json_request
from habitat.server import serve_stdio
from habitat.workspace import HabitatWorkspace


class ProtocolConformanceTests(unittest.TestCase):
    @staticmethod
    def _workspace(root: Path) -> HabitatWorkspace:
        source = root / "project"
        source.mkdir()
        (source / "main.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")
        return HabitatWorkspace.create(source, root / "state")

    def test_adversarial_transport_corpus_has_typed_safe_errors(self):
        fixture = Path(__file__).parent / "fixtures" / "protocol" / "adversarial-v1alpha2.json"
        cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
        with TemporaryDirectory() as td:
            workspace = self._workspace(Path(td))
            try:
                before = workspace.revision
                incoming = io.StringIO("\n".join(case["raw"] for case in cases) + "\n")
                outgoing = io.StringIO()

                serve_stdio(workspace, incoming, outgoing)

                responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
                self.assertEqual(before, workspace.revision)
                self.assertEqual(len(cases), len(responses))
                for case, response in zip(cases, responses):
                    self.assertFalse(response["ok"], case["id"])
                    self.assertEqual(case["error_code"], response["error"]["code"], case["id"])
                    self.assertNotIn("Traceback", response["error"]["message"])
                    self.assertNotIn("\\", response["error"]["message"])
            finally:
                workspace.close()

    def test_direct_non_object_request_is_typed_and_does_not_touch_revision(self):
        with TemporaryDirectory() as td:
            workspace = self._workspace(Path(td))
            try:
                protocol = HabitatProtocol(workspace)
                before = workspace.revision

                response = protocol.handle([])

                self.assertFalse(response["ok"])
                self.assertEqual("INVALID_REQUEST", response["error"]["code"])
                self.assertEqual(before, workspace.revision)
            finally:
                workspace.close()

    def test_oversized_transport_request_is_rejected_before_json_parsing(self):
        with self.assertRaisesRegex(ProtocolError, "size limit") as raised:
            parse_json_request("x" * (MAX_REQUEST_BYTES + 1))

        self.assertEqual("REQUEST_TOO_LARGE", raised.exception.code)

    def test_declared_read_only_calls_leave_source_and_logical_state_unchanged(self):
        with TemporaryDirectory() as td:
            workspace = self._workspace(Path(td))
            try:
                protocol = HabitatProtocol(workspace)
                source = workspace.source_root / "main.py"
                workspace.trace_start("protocol-conformance")
                before_source = source.read_bytes()
                before_revision = workspace.revision
                before_state = "\n".join(workspace.store.conn.iterdump())

                capabilities = protocol.handle({"id": "capabilities", "method": "protocol.capabilities", "params": {}})
                source_read = protocol.handle({"id": "source", "method": "workspace.source.read", "params": {"path": "main.py"}})

                self.assertTrue(capabilities["ok"])
                self.assertTrue(source_read["ok"])
                self.assertEqual(before_source, source.read_bytes())
                self.assertEqual(before_revision, workspace.revision)
                self.assertEqual(before_state, "\n".join(workspace.store.conn.iterdump()))
            finally:
                workspace.close()


if __name__ == "__main__":
    unittest.main()

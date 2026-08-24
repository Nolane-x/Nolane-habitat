import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest import mock

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

    def test_stdio_counts_whitespace_padding_in_the_wire_size_limit(self):
        with TemporaryDirectory() as td:
            workspace = self._workspace(Path(td))
            try:
                incoming = io.StringIO("{}" + (" " * MAX_REQUEST_BYTES) + "\n")
                outgoing = io.StringIO()

                serve_stdio(workspace, incoming, outgoing)

                response = json.loads(outgoing.getvalue())
                self.assertFalse(response["ok"])
                self.assertEqual("REQUEST_TOO_LARGE", response["error"]["code"])
            finally:
                workspace.close()

    def test_stdio_uses_bounded_reads_and_drains_an_oversized_line(self):
        class BoundedReader:
            def __init__(self, data: str):
                self.data = data
                self.offset = 0
                self.read_sizes = []

            def __iter__(self):
                raise AssertionError("stdio transport must not iterate unbounded lines")

            def readline(self, size: int = -1) -> str:
                if size < 0:
                    raise AssertionError("stdio transport must provide a read bound")
                self.read_sizes.append(size)
                if self.offset >= len(self.data):
                    return ""
                newline = self.data.find("\n", self.offset)
                end = len(self.data) if newline < 0 else newline + 1
                end = min(end, self.offset + size)
                chunk = self.data[self.offset:end]
                self.offset = end
                return chunk

        oversized = '{"id":"oversized"' + (" " * MAX_REQUEST_BYTES) + "}\n"
        valid = '{"id":"next","method":"protocol.capabilities","params":{}}\n'
        reader = BoundedReader(oversized + valid)
        with TemporaryDirectory() as td:
            workspace = self._workspace(Path(td))
            try:
                outgoing = io.StringIO()

                serve_stdio(workspace, reader, outgoing)

                responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
                self.assertEqual(2, len(responses))
                self.assertEqual("REQUEST_TOO_LARGE", responses[0]["error"]["code"])
                self.assertTrue(responses[1]["ok"])
                self.assertEqual("next", responses[1]["id"])
                self.assertTrue(reader.read_sizes)
                self.assertLessEqual(max(reader.read_sizes), MAX_REQUEST_BYTES + 1)
            finally:
                workspace.close()

    def test_finite_json_number_overflow_is_rejected(self):
        for number in ("1e999", "-1e999"):
            with self.subTest(number=number):
                raw = (
                    '{"id":"overflow","method":"protocol.capabilities",'
                    f'"params":{{"value":{number}}}}}'
                )
                with self.assertRaises(ProtocolError) as raised:
                    parse_json_request(raw)
                self.assertEqual("INVALID_JSON", raised.exception.code)

    def test_stdio_never_serializes_nonfinite_handler_values(self):
        request = '{"id":"strict","method":"protocol.capabilities","params":{}}\n'
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=repr(value)), TemporaryDirectory() as td:
                workspace = self._workspace(Path(td))
                try:
                    outgoing = io.StringIO()
                    with mock.patch("habitat.server.HabitatProtocol") as protocol_class:
                        protocol_class.return_value.handle.return_value = {
                            "protocol": "habitat.agent.v1alpha2",
                            "id": "strict",
                            "ok": True,
                            "revision": workspace.revision,
                            "result": {"value": value},
                        }
                        serve_stdio(workspace, io.StringIO(request), outgoing)

                    encoded = outgoing.getvalue()
                    response = json.loads(
                        encoded,
                        parse_constant=lambda token: (_ for _ in ()).throw(
                            ValueError(f"non-finite JSON token: {token}")
                        ),
                    )
                    self.assertFalse(response["ok"])
                    self.assertEqual("INTERNAL_ERROR", response["error"]["code"])
                finally:
                    workspace.close()

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

    def test_mcp_read_tools_leave_logical_state_unchanged(self):
        from habitat import mcp_adapter

        class FakeMCPServer:
            def __init__(self, _name):
                self.tools = {}
                self.resources = {}

            def tool(self):
                return lambda function: self.tools.setdefault(function.__name__, function)

            def resource(self, uri):
                return lambda function: self.resources.setdefault(uri, function)

        previous_mcp = sys.modules.get("mcp")
        previous_server = sys.modules.get("mcp.server")
        mcp_module = types.ModuleType("mcp")
        server_module = types.ModuleType("mcp.server")
        server_module.MCPServer = FakeMCPServer
        mcp_module.server = server_module
        sys.modules["mcp"] = mcp_module
        sys.modules["mcp.server"] = server_module
        try:
            with TemporaryDirectory() as td:
                root = Path(td)
                workspace = self._workspace(root)
                workspace.close()
                server, bound = mcp_adapter.build_server(root / "state")
                try:
                    object_id = bound.store.all_symbols()[0]["id"]
                    before_state = "\n".join(bound.store.conn.iterdump())

                    inspected = server.tools["habitat_inspect"](object_id, include_source="none")
                    references = server.tools["habitat_references"](object_id)

                    self.assertIsInstance(inspected, dict)
                    self.assertIsInstance(references, dict)
                    self.assertEqual(before_state, "\n".join(bound.store.conn.iterdump()))
                finally:
                    bound.close()
        finally:
            if previous_mcp is None:
                sys.modules.pop("mcp", None)
            else:
                sys.modules["mcp"] = previous_mcp
            if previous_server is None:
                sys.modules.pop("mcp.server", None)
            else:
                sys.modules["mcp.server"] = previous_server


if __name__ == "__main__":
    unittest.main()

import io
import json
import tempfile
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.server import serve_stdio
from habitat.workspace import HabitatWorkspace


class ProtocolTests(unittest.TestCase):
    def make_ws(self, root: Path):
        src = root / "p"; src.mkdir()
        (src / "main.py").write_text("def greet(name):\n    return 'hello ' + name\n")
        return HabitatWorkspace.create(src, root / "h")

    def test_agent_protocol_orient_and_inspect(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self.make_ws(Path(td)); proto = HabitatProtocol(ws)
            response = proto.handle({"id":"1","method":"workspace.orient","params":{"task":"find greet implementation"}})
            self.assertTrue(response["ok"])
            oid = response["result"]["objects"][0]["object_id"]
            inspected = proto.handle({"id":"2","method":"workspace.inspect","params":{"object_id":oid,"include_source":"body"}})
            self.assertTrue(inspected["ok"])
            self.assertIn("def greet", inspected["result"]["source"])

    def test_unknown_method_fails_typed(self):
        with tempfile.TemporaryDirectory() as td:
            proto = HabitatProtocol(self.make_ws(Path(td)))
            response = proto.handle({"id":"x","method":"shell.exec","params":{}})
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "NOT_FOUND")

    def test_stdio_transport_is_ndjson(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self.make_ws(Path(td))
            inp = io.StringIO(json.dumps({"id":1,"method":"workspace.enter","params":{}}) + "\n")
            out = io.StringIO(); serve_stdio(ws, inp, out)
            value = json.loads(out.getvalue())
            self.assertTrue(value["ok"])
            self.assertEqual(value["id"], 1)

if __name__ == "__main__": unittest.main()

import tempfile
import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace
from habitat.mutation import TransactionConflict


class WorkspaceTests(unittest.TestCase):
    def make_project(self, root: Path):
        src = root / "project"; src.mkdir()
        (src / "auth.py").write_text(
            'def validate_credentials(email, password):\n    return password == "secret"\n\n'
            'def login(email, password):\n    return validate_credentials(email, password)\n', encoding="utf-8")
        (src / "login.html").write_text('<h1>Login</h1><input id="email"><button id="submit">Sign in</button>', encoding="utf-8")
        return src

    def test_ingest_orient_inspect_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = self.make_project(root)
            ws = HabitatWorkspace.create(src, root / "hab")
            entered = ws.enter()
            self.assertEqual(entered["file_count"], 2)
            self.assertGreaterEqual(entered["symbol_count"], 4)
            ctx = ws.orient("where is login credential validation implemented")
            self.assertTrue(ctx.objects)
            first = ws.inspect(ctx.objects[0].object_id)
            self.assertEqual(first.get("name"), "validate_credentials")
            sym = next((o for o in ctx.objects if o.object_type == "symbol"), None)
            self.assertIsNotNone(sym)
            inspected = ws.inspect(sym.object_id, "body")
            self.assertIn("source", inspected)
            self.assertEqual(inspected["source_anchor"]["revision"], ws.revision)
            self.assertEqual(len(inspected["source_anchor"]["digest"]), 64)
            old = ws.revision
            (src / "auth.py").write_text((src / "auth.py").read_text() + "\nFLAG=True\n")
            # Normal agent access triggers a metadata reconciliation; no human refresh step is required.
            ws.query("FLAG")
            self.assertNotEqual(old, ws.revision)
            self.assertTrue(ws.query("FLAG"))

    def test_transaction_syncs_to_external_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = self.make_project(root)
            ws = HabitatWorkspace.create(src, root / "hab")
            tx = ws.change([{"op":"replace_text","path":"auth.py","old":"password == \"secret\"","new":"password == \"better-secret\""}])
            self.assertEqual(tx["status"], "committed")
            self.assertIn("better-secret", (src / "auth.py").read_text())

    def test_stale_digest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = self.make_project(root)
            ws = HabitatWorkspace.create(src, root / "hab")
            with self.assertRaises(TransactionConflict):
                ws.change([{"op":"replace_text","path":"auth.py","expected_digest":"deadbeef","old":"secret","new":"x"}])

    def test_staged_transaction_detects_external_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = self.make_project(root)
            ws = HabitatWorkspace.create(src, root / "hab")
            tx = ws.stage_change([{"op":"replace_text","path":"auth.py","old":"password == \"secret\"","new":"password == \"new\""}])
            (src / "auth.py").write_text((src / "auth.py").read_text() + "\n# human edit\n")
            with self.assertRaises(TransactionConflict):
                ws.commit_change(tx["id"])
            self.assertNotIn('password == "new"', (src / "auth.py").read_text())

    def test_committed_transaction_can_rollback_when_no_newer_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = self.make_project(root)
            original = (src / "auth.py").read_text()
            ws = HabitatWorkspace.create(src, root / "hab")
            tx = ws.change([{"op":"replace_text","path":"auth.py","old":"password == \"secret\"","new":"password == \"new\""}])
            rolled = ws.rollback_change(tx["id"])
            self.assertEqual(rolled["status"], "rolled-back")
            self.assertEqual((src / "auth.py").read_text(), original)

    def test_semantic_html_observation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = self.make_project(root)
            ws = HabitatWorkspace.create(src, root / "hab")
            ui = ws.observe_ui("login.html")
            roles = {e["role"] for e in ui["elements"]}
            names = {e["name"] for e in ui["elements"] if e["name"]}
            self.assertIn("button", roles); self.assertIn("Sign in", names)
            self.assertTrue(ui["limitations"])

if __name__ == "__main__": unittest.main()

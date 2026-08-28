import tempfile
import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace
from habitat.ui import BrowserRuntime


class Alpha1SemanticTests(unittest.TestCase):
    def make_project(self, root: Path):
        src = root / "project"; src.mkdir()
        (src / "auth.py").write_text('def validate_credentials(email, password):\n    return password == "secret"\n', encoding="utf-8")
        (src / "helper.py").write_text('def helper():\n    return 1\n', encoding="utf-8")
        tests = src / "tests"; tests.mkdir()
        (tests / "test_auth.py").write_text('import unittest\nimport auth\n\nclass AuthTest(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(auth.validate_credentials("a", "secret"))\n', encoding="utf-8")
        return src

    def test_incremental_refresh_recompiles_only_changed_file(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            (src/"helper.py").write_text('def helper():\n    return 2\n', encoding="utf-8")
            result=ws.refresh("test-change")
            self.assertEqual(result["compiled_files"], 1)
            self.assertGreaterEqual(result["reused_files"], 2)

    def test_context_compiler_v2_pages_without_source_dump(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            ctx=ws.orient("fix credential validation regression and verify tests", budget=3)
            self.assertEqual(ctx.task_class, "implementation")
            self.assertIsNotNone(ctx.handle)
            self.assertLessEqual(len(ctx.objects),3)
            page=ws.context_page(ctx.handle,0,10)
            self.assertFalse(page["stale"])
            self.assertGreaterEqual(page["total"],len(ctx.objects))
            self.assertTrue(all("source" not in o for o in page["objects"]))

    def test_semantic_symbol_transaction_has_preview_and_syncs_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            sym=next(s for s in ws.store.all_symbols() if s["name"]=="validate_credentials")
            tx=ws.stage_symbol_change(sym["id"], 'def validate_credentials(email, password):\n    return password == "better"')
            self.assertEqual(tx["status"],"staged"); self.assertIn("better",tx["preview"][0]["unified_diff"])
            out=ws.commit_change(tx["id"])
            self.assertEqual(out["status"],"committed")
            self.assertIn('password == "better"',(src/"auth.py").read_text())

    def test_verification_plan_links_importing_test_file(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            plan=ws.verification_plan(changed_paths=["auth.py"])
            self.assertIn("tests/test_auth.py",plan["linked_test_files"])
            self.assertTrue(any(c["kind"]=="test" for c in plan["test_capabilities"]))

    def test_test_run_returns_structured_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            result=ws.run("python.unittest",timeout_s=20)
            self.assertEqual(result["exit_code"],0)
            self.assertEqual(result["structured"]["framework"],"unittest")
            self.assertEqual(result["structured"]["total"],1)
            self.assertEqual(result["structured"]["status"],"passed")

    def test_checkpoint_resume_marks_changed_resident_object_stale(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            sym=next(s for s in ws.store.all_symbols() if s["name"]=="validate_credentials")
            cp=ws.checkpoint("continue auth work",[sym["id"]])
            first=ws.resume(cp["id"]); self.assertEqual(len(first["fresh_objects"]),1)
            (src/"auth.py").write_text((src/"auth.py").read_text()+"\n# external\n")
            second=ws.resume(cp["id"])
            self.assertTrue(second["reorient_recommended"])
            self.assertEqual(len(second["stale_objects"]),1)

    def test_source_paging_is_bounded_and_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            page=ws.read_source("auth.py",1,1)
            self.assertEqual(page["source"],"def validate_credentials(email, password):")
            self.assertEqual(page["next_line"],2)

    @unittest.skipUnless(BrowserRuntime.probe()["available"], "runtime browser unavailable")
    def test_runtime_ui_semantic_action_and_source_hint(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"project"; src.mkdir()
            (src/"index.html").write_text('''<!doctype html><html><body><label for="name">Name</label><input id="name"><button id="go" onclick="document.getElementById('out').textContent='Hello '+document.getElementById('name').value">Go</button><div id="out" role="status"></div></body></html>''',encoding="utf-8")
            ws=HabitatWorkspace.create(src,root/"hab")
            opened=ws.open_ui_runtime("index.html")
            by={e["handle"]:e for e in opened["elements"]}
            self.assertEqual(by["ui:id:name"]["name"],"Name")
            self.assertTrue(by["ui:id:go"].get("source_hints"))
            sid=opened["session_id"]
            ws.act_ui_runtime(sid,"fill","ui:id:name","Nolane")
            result=ws.act_ui_runtime(sid,"click","ui:id:go")
            out=next(e for e in result["elements"] if e["handle"]=="ui:id:out")
            self.assertEqual(out["text"],"Hello Nolane")
            self.assertTrue(any(c["handle"]=="ui:id:out" for c in result["delta"]["changed"]))
            ws.close_ui_runtime(sid)

    def test_context_handle_becomes_stale_after_revision_change(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=self.make_project(root); ws=HabitatWorkspace.create(src, root/"hab")
            ctx=ws.orient("credential validation", budget=2)
            (src/"helper.py").write_text('def helper():\n    return 3\n', encoding="utf-8")
            ws.refresh("external-change")
            page=ws.context_page(ctx.handle,0,10)
            self.assertTrue(page["stale"])
            self.assertEqual(page["objects"],[])

    def test_semantic_mutation_refuses_non_authoritative_java_parser_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"project"; src.mkdir()
            (src/"A.java").write_text('public class A { public void run() { } }',encoding="utf-8")
            ws=HabitatWorkspace.create(src,root/"hab")
            sym=next(iter(ws.store.all_symbols()))
            self.assertEqual(sym["trust"],"parser")
            with self.assertRaises(Exception):
                ws.stage_symbol_change(sym["id"],'public class A { }')

    def test_typescript_parser_diagnostic_is_first_class_when_provider_available(self):
        from habitat.semantic.typescript import TypeScriptCompilerProvider
        if not TypeScriptCompilerProvider().available()[0]:
            self.skipTest("TypeScript compiler provider unavailable")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"project"; src.mkdir(); (src/"bad.ts").write_text('export function broken( {\n')
            ws=HabitatWorkspace.create(src,root/"hab")
            diags=ws.store.all_diagnostics(); self.assertEqual(len(diags),1)
            inspected=ws.inspect(diags[0]["id"])
            self.assertEqual(inspected["path"],"bad.ts"); self.assertEqual(inspected["source"],"typescript-compiler-api")

    @unittest.skipUnless(BrowserRuntime.probe()["available"], "runtime browser unavailable")
    def test_runtime_ui_loads_project_external_script_without_terminal_server(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"project"; src.mkdir()
            (src/"index.html").write_text('<button id="go">Go</button><div id="out"></div><script src="app.js"></script>',encoding="utf-8")
            (src/"app.js").write_text("document.getElementById('go').addEventListener('click',()=>document.getElementById('out').textContent='external works')",encoding="utf-8")
            ws=HabitatWorkspace.create(src,root/"hab")
            opened=ws.open_ui_runtime("index.html"); result=ws.act_ui_runtime(opened["session_id"],"click","ui:id:go")
            out=next(e for e in result["elements"] if e["handle"]=="ui:id:out")
            self.assertEqual(out["text"],"external works")
            ws.close()

    @unittest.skipUnless(BrowserRuntime.probe()["available"], "runtime browser unavailable")
    def test_runtime_resource_router_blocks_escape_outside_source_root(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"project"; src.mkdir()
            (root/"outside.js").write_text("document.title='ESCAPED'",encoding="utf-8")
            (src/"index.html").write_text('<script src="../outside.js"></script><h1 id="ok">Safe</h1>',encoding="utf-8")
            ws=HabitatWorkspace.create(src,root/"hab")
            opened=ws.open_ui_runtime("index.html")
            self.assertNotEqual(opened["title"],"ESCAPED")
            ws.close()

if __name__ == "__main__": unittest.main()

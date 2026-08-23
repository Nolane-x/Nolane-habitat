import tempfile
import unittest
from pathlib import Path

from habitat.workspace import HabitatWorkspace
from habitat.ui import BrowserRuntime


class Alpha5MerkleTests(unittest.TestCase):
    def test_merkle_state_diff_and_exact_rename_detection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir(); (root/'src').mkdir()
            (root/'src'/'a.py').write_text('def alpha():\n    return 1\n',encoding='utf-8')
            (root/'src'/'b.py').write_text('def beta():\n    return 2\n',encoding='utf-8')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                r1=ws.revision; state=ws.state_merkle(prefix='src')
                self.assertEqual(state['source_bytes_read'],0)
                self.assertEqual(state['node']['file_count'],2)
                (root/'src'/'a.py').write_text('def alpha():\n    return 3\n',encoding='utf-8')
                ws.refresh(reason='modify-a'); r2=ws.revision
                diff=ws.state_merkle_diff(r1,r2,prefix='src')
                self.assertEqual(diff['modified'],['src/a.py'])
                self.assertEqual(diff['source_bytes_read'],0)
                before=ws.store.merkle_stats()['objects']
                (root/'src'/'b.py').rename(root/'src'/'renamed.py')
                ws.refresh(reason='rename-b'); r3=ws.revision
                move=ws.state_merkle_diff(r2,r3,prefix='src')
                self.assertEqual(move['renamed'][0]['from'],'src/b.py')
                self.assertEqual(move['renamed'][0]['to'],'src/renamed.py')
                # Content-addressed objects should reuse the unchanged file blob across path rename.
                after=ws.store.merkle_stats()['objects']
                self.assertLess(after-before,5)
            finally: ws.close()

    def test_equal_subtree_diff_is_pruned(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir(); (root/'pkg').mkdir()
            (root/'pkg'/'x.py').write_text('x=1\n'); (root/'outside.txt').write_text('a')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                r1=ws.revision
                (root/'outside.txt').write_text('b'); ws.refresh(reason='outside'); r2=ws.revision
                d=ws.state_merkle_diff(r1,r2,prefix='pkg')
                self.assertFalse(d['changed']); self.assertTrue(d['pruned_equal_subtree'])
            finally: ws.close()


class Alpha5VirtualContextTests(unittest.TestCase):
    def test_address_space_and_exact_page_fault(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir()
            (root/'auth.py').write_text('def validate_credentials(value):\n    return bool(value)\n\ndef unrelated():\n    return 7\n',encoding='utf-8')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                ctx=ws.orient('fix credential validation implementation',budget=8)
                space=ws.context_address_space(ctx.handle)
                pages=[p for p in space['pages'] if p['fetchable']]
                self.assertTrue(pages)
                target=next(p for p in pages if 'validate' in (ws.store.symbol_by_id(p['object_id'])['name'] if ws.store.symbol_by_id(p['object_id']) else ''))
                fetched=ws.context_fetch_pages(ctx.handle,[target['page_id']],max_source_bytes=5000)
                self.assertEqual(fetched['faults'],[])
                self.assertIn('def validate_credentials',fetched['pages'][0]['source'])
                self.assertEqual(fetched['pages'][0]['authority'],'exact-source')
                tiny=ws.context_fetch_pages(ctx.handle,[target['page_id']],max_source_bytes=1)
                self.assertEqual(tiny['pages'],[]); self.assertEqual(tiny['faults'][0]['reason'],'byte-budget')
            finally: ws.close()

    def test_stale_context_pages_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir(); f=root/'a.py'; f.write_text('def work():\n    return 1\n')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                ctx=ws.orient('work implementation',budget=5); space=ws.context_address_space(ctx.handle)
                pid=next(p['page_id'] for p in space['pages'] if p['fetchable'])
                f.write_text('def work():\n    return 2\n'); ws.refresh(reason='edit')
                result=ws.context_fetch_pages(ctx.handle,[pid])
                self.assertTrue(result['stale']); self.assertEqual(result['faults'][0]['reason'],'context-revision-stale')
            finally: ws.close()


@unittest.skipUnless(BrowserRuntime.probe().get('available'),'runtime browser unavailable')
class Alpha5UiAssertionTests(unittest.TestCase):
    def test_semantic_assertions_without_pixels(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir()
            (root/'index.html').write_text('''<input id="name" aria-label="Name"><button id="go">Go</button><div id="out"></div><script>document.getElementById('go').onclick=()=>{document.getElementById('out').textContent='Hello '+document.getElementById('name').value}</script>''',encoding='utf-8')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                opened=ws.open_ui_runtime('index.html'); sid=opened['session_id']
                ws.act_ui_runtime(sid,'fill','ui:id:name','Nolane'); ws.act_ui_runtime(sid,'click','ui:id:go')
                result=ws.assert_ui_runtime(sid,[
                    {'handle':'ui:id:out','text':'Hello Nolane','visible':True},
                    {'role':'button','name':'Go','min_count':1,'enabled':True},
                ])
                self.assertTrue(result['passed'],result)
                self.assertFalse(result['screenshot_used'])
                bad=ws.assert_ui_runtime(sid,[{'handle':'ui:id:out','text':'Wrong'}])
                self.assertFalse(bad['passed']); self.assertEqual(bad['failure_count'],1)
            finally: ws.close()


if __name__=='__main__': unittest.main()

class Alpha5EvidenceTests(unittest.TestCase):
    def test_test_failure_becomes_active_context_evidence_and_resolves_on_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir(); (root/'tests').mkdir()
            impl=root/'calc.py'; impl.write_text('def add(a,b):\n    return a-b\n')
            (root/'tests'/'test_calc.py').write_text('from calc import add\n\ndef test_addition():\n    assert add(2,3)==5\n')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                result=ws.verify(changed_paths=['calc.py'])
                self.assertNotEqual(result['receipt']['exit_code'],0)
                active=ws.evidence_active('test-failure')
                self.assertGreaterEqual(active['count'],1)
                eid=active['evidence'][0]['id']
                inspected=ws.inspect(eid)
                self.assertEqual(inspected['kind'],'test-failure'); self.assertTrue(inspected['active'])
                ctx=ws.orient('fix failing addition test',budget=12)
                self.assertTrue(any(o.object_type=='evidence' for o in ctx.objects),[(o.object_type,o.reason) for o in ctx.objects])
                impl.write_text('def add(a,b):\n    return a+b\n'); ws.refresh(reason='fix')
                passed=ws.verify(changed_paths=['calc.py'])
                self.assertEqual(passed['receipt']['exit_code'],0,passed['receipt']['stdout']+passed['receipt']['stderr'])
                self.assertEqual(ws.evidence_active('test-failure')['count'],0)
            finally: ws.close()

class Alpha5McpAdapterTests(unittest.TestCase):
    def test_compact_tool_catalog_and_composed_start_task(self):
        from habitat.mcp_adapter import tool_catalog, compose_start_task
        tools=tool_catalog(); names={x['name'] for x in tools}
        self.assertLessEqual(len(tools),12)
        self.assertIn('habitat_start_task',names); self.assertIn('habitat_ui_assert',names)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir(); (root/'a.py').write_text('def solve_widget(x):\n    return x\n')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                result=compose_start_task(ws,'change widget solving implementation',budget=8,source_budget=4000)
                self.assertEqual(result['revision'],ws.revision)
                self.assertGreaterEqual(result['source_packet']['source_bytes'],1)
                self.assertIn('whole-file dump disabled',result['policy'])
            finally: ws.close()

    def test_mcp_dependency_is_optional_and_failure_is_typed(self):
        import importlib.util
        from habitat.mcp_adapter import build_server
        if importlib.util.find_spec('mcp') is None:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td)/'p'; root.mkdir(); (root/'a.py').write_text('x=1\n')
                ws=HabitatWorkspace.create(root,Path(td)/'h'); ws.close()
                with self.assertRaisesRegex(RuntimeError,'optional'):
                    build_server(Path(td)/'h')


    def test_mcp_adapter_registers_compact_surface_against_sdk_contract_double(self):
        import sys, types
        from habitat import mcp_adapter
        class FakeMCPServer:
            def __init__(self,name): self.name=name; self.tools={}; self.resources={}
            def tool(self):
                def deco(fn): self.tools[fn.__name__]=fn; return fn
                return deco
            def resource(self,uri):
                def deco(fn): self.resources[uri]=fn; return fn
                return deco
            def run(self): return None
        old_mcp=sys.modules.get('mcp'); old_server=sys.modules.get('mcp.server')
        mod=types.ModuleType('mcp'); server=types.ModuleType('mcp.server'); server.MCPServer=FakeMCPServer; mod.server=server
        sys.modules['mcp']=mod; sys.modules['mcp.server']=server
        try:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td)/'p';root.mkdir();(root/'a.py').write_text('def alpha():\n    return 1\n')
                ws=HabitatWorkspace.create(root,Path(td)/'h'); ws.close()
                mcp,bound=mcp_adapter.build_server(Path(td)/'h')
                self.assertEqual(set(mcp.tools),{x['name'] for x in mcp_adapter.tool_catalog()})
                self.assertEqual(len(mcp.tools),12)
                self.assertIn('habitat://status',mcp.resources)
                bound.close()
        finally:
            if old_mcp is None: sys.modules.pop('mcp',None)
            else: sys.modules['mcp']=old_mcp
            if old_server is None: sys.modules.pop('mcp.server',None)
            else: sys.modules['mcp.server']=old_server


class SemanticRenameTests(unittest.TestCase):
    def test_python_jedi_rename_updates_definition_and_original_import_but_preserves_alias(self):
        try:
            import jedi  # noqa: F401
        except Exception:
            self.skipTest("Jedi unavailable")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"auth.py").write_text("def validate_credentials(value):\n    return bool(value)\n",encoding="utf-8")
            (root/"service.py").write_text("from auth import validate_credentials as check\n\ndef login(value):\n    return check(value)\n",encoding="utf-8")
            ws=HabitatWorkspace.create(root,Path(td)/"ws")
            sym=next(x for x in ws.store.all_symbols() if x["path"]=="auth.py" and x["name"]=="validate_credentials")
            tx=ws.stage_symbol_rename(sym["id"],"verify_credentials")
            self.assertEqual(tx["semantic_rename"]["site_count"],2)
            ws.commit_change(tx["id"])
            self.assertIn("def verify_credentials",(root/"auth.py").read_text())
            service=(root/"service.py").read_text()
            self.assertIn("from auth import verify_credentials as check",service)
            self.assertIn("return check(value)",service)
            self.assertNotIn("validate_credentials",(root/"auth.py").read_text()+service)

    def test_rename_is_stale_digest_bound(self):
        try:
            import jedi  # noqa: F401
        except Exception:
            self.skipTest("Jedi unavailable")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"a.py").write_text("def thing():\n    return 1\n",encoding="utf-8")
            (root/"b.py").write_text("from a import thing\n\ndef use():\n    return thing()\n",encoding="utf-8")
            ws=HabitatWorkspace.create(root,Path(td)/"ws")
            sym=next(x for x in ws.store.all_symbols() if x["path"]=="a.py" and x["name"]=="thing")
            tx=ws.stage_symbol_rename(sym["id"],"renamed")
            (root/"b.py").write_text((root/"b.py").read_text()+"# external edit\n",encoding="utf-8")
            with self.assertRaises(Exception): ws.commit_change(tx["id"])


class SelectiveRetrievalTests(unittest.TestCase):
    def test_concept_coverage_recognizes_identifier_morphology_without_noise(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"auth.py").write_text("def validate_credentials(value):\n    return bool(value)\n",encoding="utf-8")
            (root/"service.py").write_text("from auth import validate_credentials\n\ndef login(value):\n    return validate_credentials(value)\n",encoding="utf-8")
            ws=HabitatWorkspace.create(root,Path(td)/"ws")
            ctx=ws.orient("fix credential validation login",8)
            self.assertEqual(ctx.decision_packet["retrieval_confidence"],"high",ctx.decision_packet)
            self.assertFalse(ctx.decision_packet["abstention_recommended"])
            self.assertGreaterEqual(ctx.decision_packet["concept_coverage"],0.99)

    def test_no_gold_task_recommends_abstention_and_mcp_suppresses_source_prefetch(self):
        from habitat.mcp_adapter import compose_start_task
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"auth.py").write_text("def login(user):\n    return bool(user)\n",encoding="utf-8")
            ws=HabitatWorkspace.create(root,Path(td)/"ws")
            ctx=ws.orient("quantum banana teleportation matrix",8)
            self.assertTrue(ctx.decision_packet["abstention_recommended"],ctx.decision_packet)
            start=compose_start_task(ws,"quantum banana teleportation matrix",8,5000)
            self.assertTrue(start["abstained"])
            self.assertEqual(start["source_packet"]["source_bytes"],0)

    def test_resolved_evidence_is_not_retrieved_via_fts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"calc.py").write_text("def add(a,b):\n    return a-b\n",encoding="utf-8")
            tests=root/"tests"; tests.mkdir()
            (tests/"test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2,3)==5\n",encoding="utf-8")
            ws=HabitatWorkspace.create(root,Path(td)/"ws")
            failed=ws.verify(changed_paths=["calc.py"],timeout_s=30)
            self.assertNotEqual(failed["receipt"]["structured"]["status"],"passed")
            self.assertGreater(ws.evidence_active("test-failure")["count"],0)
            sym=next(x for x in ws.store.all_symbols() if x["path"]=="calc.py" and x["name"]=="add")
            tx=ws.stage_symbol_change(sym["id"],"def add(a,b):\n    return a+b")
            ws.commit_change(tx["id"])
            passed=ws.verify(changed_paths=["calc.py"],timeout_s=30)
            self.assertEqual(passed["receipt"]["structured"]["status"],"passed",passed["receipt"]["stdout"]+passed["receipt"]["stderr"])
            self.assertEqual(ws.evidence_active("test-failure")["count"],0)
            ctx=ws.orient("fix failing addition test",12)
            self.assertFalse(any(o.object_type=="evidence" for o in ctx.objects),ctx.objects)


class TypeScriptPartitionTests(unittest.TestCase):
    def test_typescript_dirty_source_traversal_partitions(self):
        from habitat.semantic.typescript import TypeScriptCompilerProvider
        if not TypeScriptCompilerProvider().available()[0]:
            self.skipTest("TypeScript provider unavailable")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"project"; root.mkdir()
            (root/"a.ts").write_text("export function a(){ return 1 }\n",encoding="utf-8")
            (root/"b.ts").write_text("import {a} from './a'; export function b(){ return a() }\n",encoding="utf-8")
            (root/"c.ts").write_text("export function c(){ return 3 }\n",encoding="utf-8")
            ws=HabitatWorkspace.create(root,Path(td)/"ws")
            warm=ws.refresh(reason="ts-warm")
            rep=ws.semantic_provider_report()["providers"]["typescript-program"]
            self.assertEqual(rep["partitions_recomputed"],0,rep)
            self.assertFalse(rep["program_invoked"],rep)
            (root/"a.ts").write_text("export function a(){ return 2 }\n",encoding="utf-8")
            ws.refresh(reason="ts-body-only")
            body=ws.semantic_provider_report()["providers"]["typescript-program"]
            self.assertEqual(body["partitions_recomputed"],1,body)
            self.assertEqual(body["partitions_reused"],2,body)
            self.assertTrue(body["program_invoked"],body)
            self.assertEqual(body["scanned_files"],1,body)
            (root/"a.ts").write_text("export function a(){ return 2 }\nexport function added(){ return 4 }\n",encoding="utf-8")
            ws.refresh(reason="ts-api-surface")
            surf=ws.semantic_provider_report()["providers"]["typescript-program"]
            self.assertEqual(surf["partitions_recomputed"],3,surf)
            self.assertEqual(surf["scanned_files"],3,surf)


import tempfile
import unittest
from pathlib import Path

from habitat.semantic.typescript import TypeScriptCompilerProvider
from habitat.workspace import HabitatWorkspace
from habitat.ui import BrowserRuntime
from habitat.protocol import HabitatProtocol, PROTOCOL_VERSION


class Alpha2SemanticLoopTests(unittest.TestCase):
    def test_python_qualified_call_disambiguates_duplicate_names(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def validate(value):\n    return value == "ok"\n')
            (p/'other.py').write_text('def validate(value):\n    return False\n')
            (p/'service.py').write_text('import auth\n\ndef run(v):\n    return auth.validate(v)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            run=next(x for x in ws.store.all_symbols() if x['path']=='service.py' and x['name']=='run')
            auth=next(x for x in ws.store.all_symbols() if x['path']=='auth.py' and x['name']=='validate')
            other=next(x for x in ws.store.all_symbols() if x['path']=='other.py' and x['name']=='validate')
            calls=[dict(r) for r in ws.store.relations_for(run['id']) if r['source_id']==run['id'] and r['kind']=='calls']
            self.assertTrue(any(r['target_id']==auth['id'] and r['trust']=='semantic' for r in calls), calls)
            self.assertFalse(any(r['target_id']==other['id'] and r['trust'] in {'semantic','parser','derived'} for r in calls), calls)
            refs=ws.references(auth['id'])
            self.assertTrue(any(o['path']=='service.py' and o['role']=='call' for o in refs['occurrences']))

    def test_python_from_import_alias_resolves_target(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def validate(value):\n    return True\n')
            (p/'main.py').write_text('from auth import validate as check\n\ndef run(v):\n    return check(v)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            run=next(x for x in ws.store.all_symbols() if x['name']=='run')
            target=next(x for x in ws.store.all_symbols() if x['path']=='auth.py' and x['name']=='validate')
            self.assertTrue(any(r['target_id']==target['id'] and r['kind']=='calls' and r['trust']=='semantic' for r in ws.store.relations_for(run['id'])))

    def test_python_relative_import_resolves_inside_package(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); pkg=p/'pkg'; pkg.mkdir(); (pkg/'__init__.py').write_text('')
            (pkg/'auth.py').write_text('def validate(v):\n    return v\n')
            (pkg/'service.py').write_text('from .auth import validate as check\n\ndef run(v):\n    return check(v)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            run=next(x for x in ws.store.all_symbols() if x['path']=='pkg/service.py' and x['name']=='run')
            target=next(x for x in ws.store.all_symbols() if x['path']=='pkg/auth.py' and x['name']=='validate')
            self.assertTrue(any(r['kind']=='calls' and r['target_id']==target['id'] and r['trust']=='semantic' for r in ws.store.relations_for(run['id'])))

    @unittest.skipUnless(TypeScriptCompilerProvider().available()[0], 'TypeScript compiler unavailable')
    def test_typescript_program_disambiguates_duplicate_exports(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.ts').write_text('export function work(){ return "a" }\n')
            (p/'b.ts').write_text('export function work(){ return "b" }\n')
            (p/'main.ts').write_text('import {work} from "./a"; export function run(){ return work(); }\n')
            ws=HabitatWorkspace.create(p,root/'h')
            run=next(x for x in ws.store.all_symbols() if x['path']=='main.ts' and x['name']=='run')
            a=next(x for x in ws.store.all_symbols() if x['path']=='a.ts' and x['name']=='work')
            b=next(x for x in ws.store.all_symbols() if x['path']=='b.ts' and x['name']=='work')
            calls=[dict(r) for r in ws.store.relations_for(run['id']) if r['source_id']==run['id'] and r['kind']=='calls']
            self.assertTrue(any(r['target_id']==a['id'] and r['trust']=='semantic' for r in calls), calls)
            self.assertFalse(any(r['target_id']==b['id'] and r['trust']=='semantic' for r in calls), calls)

    def test_context_v3_semantic_path_breaks_duplicate_name_tie(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def validate_credentials(email,password):\n    return True\n')
            (p/'other.py').write_text('def validate_credentials(email,password):\n    return False\n')
            (p/'service.py').write_text('import auth\n\ndef login(e,p):\n    return auth.validate_credentials(e,p)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            ctx=ws.orient('fix credential validation in login behavior',budget=8)
            auth=next(o for o in ctx.objects if o.path=='auth.py' and ws.store.symbol_by_id(o.object_id))
            other=next(o for o in ctx.objects if o.path=='other.py' and ws.store.symbol_by_id(o.object_id))
            self.assertGreater(auth.relevance,other.relevance)
            self.assertIn('graph',auth.lane)

    def test_event_journal_records_external_modify_and_diff(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); f=p/'a.py'; f.write_text('def f():\n    return 1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            old=ws.revision; cursor=ws.store.latest_event_seq()
            f.write_text('def f():\n    return 2\n')
            events=ws.events_poll(cursor)
            self.assertNotEqual(ws.revision,old)
            self.assertTrue(any(e['kind']=='file-modified' and e['path']=='a.py' for e in events['events']))
            diff=ws.diff_since(old)
            self.assertTrue(diff['reachable']); self.assertEqual(diff['changed_paths'],['a.py'])

    def test_affected_test_graph_prefers_reaching_test(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'tests').mkdir()
            (p/'auth.py').write_text('def validate(x):\n    return x\n')
            (p/'other.py').write_text('def noop():\n    return 1\n')
            (p/'tests'/'test_auth.py').write_text('import unittest\nimport auth\nclass T(unittest.TestCase):\n    def test_auth(self):\n        self.assertTrue(auth.validate(True))\n')
            (p/'tests'/'test_other.py').write_text('import unittest\nimport other\nclass T(unittest.TestCase):\n    def test_other(self):\n        self.assertEqual(other.noop(),1)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            target=next(x for x in ws.store.all_symbols() if x['path']=='auth.py' and x['name']=='validate')
            impact=ws.impact(object_ids=[target['id']])
            paths=[x['path'] for x in impact['ranked_test_files']]
            self.assertIn('tests/test_auth.py',paths)
            self.assertNotIn('tests/test_other.py',paths)
            out=ws.verify(object_ids=[target['id']],timeout_s=20)
            sel=out['receipt']['structured']['selection']
            self.assertIn('tests/test_auth.py',sel['selected_test_files'])
            self.assertEqual(out['receipt']['exit_code'],0)

    def test_noop_refresh_reuses_project_semantic_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('def f():\n    return 1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            out=ws.refresh('noop')
            self.assertTrue(out['unchanged'])
            self.assertTrue(out['project_semantic_cache_hit'])
            self.assertEqual(out['compiled_files'],0)

    def test_legacy_compile_cache_is_recompiled_once_instead_of_trusted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def validate(v):\n    return v\n')
            (p/'service.py').write_text('import auth\n\ndef run(v):\n    return auth.validate(v)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            auth_row=ws.store.file_by_path('auth.py')
            cache=ws.store.load_compile_cache(auth_row['id'])
            # Simulate an alpha.1 cache record: source digest is still current but the
            # compiler artifact has no version/fingerprint contract.
            cache.pop('compiler_cache_version',None); cache.pop('fingerprint',None)
            ws.store.save_compile_cache(auth_row['id'],cache); ws.store.commit()
            out=ws.refresh('upgrade-alpha1-cache')
            self.assertEqual(out['compiled_files'],1)
            self.assertFalse(out['project_semantic_cache_hit'])
            run=next(x for x in ws.store.all_symbols() if x['path']=='service.py' and x['name']=='run')
            auth=next(x for x in ws.store.all_symbols() if x['path']=='auth.py' and x['name']=='validate')
            self.assertTrue(any(r['kind']=='calls' and r['target_id']==auth['id'] and r['trust']=='semantic' for r in ws.store.relations_for(run['id'])))
            # The migration is one-shot: a subsequent no-op can reuse all artifacts.
            again=ws.refresh('post-upgrade-noop')
            self.assertEqual(again['compiled_files'],0)
            self.assertTrue(again['project_semantic_cache_hit'])

    def test_project_semantic_cache_rejects_provider_fingerprint_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('def f():\n    return 1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            cached=ws.store.load_project_cache('semantic-project-v2')
            cached['provider_fingerprint']={'project_semantics_version':-1,'typescript_version':'impossible'}
            ws.store.save_project_cache('semantic-project-v2',cached); ws.store.commit()
            out=ws.refresh('provider-fingerprint-probe')
            self.assertEqual(out['compiled_files'],0)
            self.assertFalse(out['project_semantic_cache_hit'])
            again=ws.refresh('provider-fingerprint-settled')
            self.assertTrue(again['project_semantic_cache_hit'])

    def test_provider_report_does_not_pretend_tree_sitter_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('x=1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            report=ws.semantic_provider_report()
            self.assertIn('tree-sitter',report['providers'])
            self.assertFalse(report['providers']['tree-sitter']['available'])

    @unittest.skipUnless(BrowserRuntime.probe()["available"], "runtime browser unavailable")
    def test_runtime_listener_source_hint_maps_external_js(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'index.html').write_text('<button data-testid="save">Save</button><div id="out"></div><script src="app.js"></script>')
            (p/'app.js').write_text("document.querySelector('[data-testid=save]').addEventListener('click',()=>document.getElementById('out').textContent='saved')\n")
            ws=HabitatWorkspace.create(p,root/'h')
            opened=ws.open_ui_runtime('index.html')
            button=next(e for e in opened['elements'] if e['attrs'].get('data-testid')=='save')
            hints=button.get('source_hints',[])
            self.assertTrue(any(h['path']=='app.js' and h['relation'].startswith('runtime-event-listener:click') and h['trust']=='semantic' for h in hints), hints)
            result=ws.act_ui_runtime(opened['session_id'],'click',button['handle'])
            out=next(e for e in result['elements'] if e['handle']=='ui:id:out')
            self.assertEqual(out['text'],'saved')
            ws.close()

    @unittest.skipUnless(TypeScriptCompilerProvider().available()[0], 'TypeScript compiler unavailable')
    def test_typescript_semantic_ingestion_does_not_execute_project_code(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); marker=root/'EXECUTED'
            (p/'evil.ts').write_text("import {execSync} from 'child_process'; execSync('touch %s'); export function f(){return 1}" % marker.as_posix())
            HabitatWorkspace.create(p,root/'h')
            self.assertFalse(marker.exists())

    @unittest.skipUnless(BrowserRuntime.probe()["available"], "runtime browser unavailable")
    def test_multiple_workspace_browser_runtimes_share_engine_without_cross_invalidating(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p1=root/'p1'; p2=root/'p2'; p1.mkdir(); p2.mkdir()
            (p1/'index.html').write_text('<h1 id="one">One</h1>'); (p2/'index.html').write_text('<h1 id="two">Two</h1>')
            w1=HabitatWorkspace.create(p1,root/'h1'); w2=HabitatWorkspace.create(p2,root/'h2')
            o1=w1.open_ui_runtime('index.html'); o2=w2.open_ui_runtime('index.html')
            self.assertEqual(next(e for e in o1['elements'] if e['handle']=='ui:id:one')['text'],'One')
            self.assertEqual(next(e for e in o2['elements'] if e['handle']=='ui:id:two')['text'],'Two')
            w1.close()
            # Closing one workspace must not kill the shared engine used by another workspace.
            again=w2.observe_ui_runtime(o2['session_id']); self.assertEqual(again['title'],'')
            w2.close()

    def test_protocol_alpha2_exposes_semantic_loop_methods(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('def f():\n    return 1\n')
            proto=HabitatProtocol(HabitatWorkspace.create(p,root/'h'))
            caps=proto.handle({'id':1,'method':'protocol.capabilities','params':{}})
            self.assertEqual(PROTOCOL_VERSION,'habitat.agent.v1alpha2')
            for method in ['workspace.references','workspace.impact','workspace.verification.run','workspace.events.poll','workspace.diff.since','workspace.semantic.providers']:
                self.assertIn(method,caps['result']['methods'])

if __name__=='__main__': unittest.main()

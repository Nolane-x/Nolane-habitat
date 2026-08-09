import os
import json
import tempfile
import time
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.semantic.typescript import TypeScriptCompilerProvider
from habitat.ui import BrowserRuntime
from habitat.workspace import HabitatWorkspace


class Alpha3LiveWorkspaceTests(unittest.TestCase):
    def test_reconcile_hashes_only_metadata_changed_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def a():\n    return 1\n')
            (p/'b.py').write_text('def b():\n    return 2\n')
            ws=HabitatWorkspace.create(p,root/'h')
            (p/'a.py').write_text('def a():\n    return 3\n')
            out=ws.reconcile()
            self.assertEqual(out['refresh_mode'],'targeted')
            self.assertEqual(out['hashed_files'],1)
            self.assertEqual(out['compiled_files'],1)
            self.assertEqual(out['changed_paths'],['a.py'])

    def test_noop_graph_sync_does_not_rewrite_edges(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def work():\n    return 1\n')
            (p/'b.py').write_text('from a import work\ndef run():\n    return work()\n')
            ws=HabitatWorkspace.create(p,root/'h')
            out=ws.refresh('noop-graph-delta')
            rel=out['graph_delta']['relations']; occ=out['graph_delta']['occurrences']
            self.assertEqual((rel['inserted'],rel['updated'],rel['deleted']),(0,0,0))
            self.assertEqual((occ['inserted'],occ['updated'],occ['deleted']),(0,0,0))
            self.assertGreater(rel['unchanged'],0)
            self.assertGreater(occ['unchanged'],0)

    def test_document_edit_reuses_semantic_provider_domains(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def f():\n    return 1\n')
            (p/'README.md').write_text('first\n')
            ws=HabitatWorkspace.create(p,root/'h')
            ws.refresh('settle-cache')
            (p/'README.md').write_text('second and changed\n')
            out=ws.reconcile()
            reuse=out['project_semantics']['cache']['provider_domain_reuse']
            self.assertTrue(reuse['base'])
            self.assertTrue(reuse['typescript'])
            self.assertEqual(out['compiled_files'],1)
            self.assertEqual(out['graph_delta']['relations']['inserted'],0)
            self.assertEqual(out['graph_delta']['relations']['deleted'],0)

    @unittest.skipUnless(TypeScriptCompilerProvider().available()[0], 'TypeScript compiler unavailable')
    def test_python_edit_does_not_rerun_typescript_project_domain(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'app.ts').write_text('export function work(){ return 1 }\n')
            (p/'a.py').write_text('def f():\n    return 1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            ws.refresh('settle-cache')
            (p/'a.py').write_text('def f():\n    return 2\n')
            out=ws.reconcile()
            self.assertTrue(out['project_semantics']['typescript-project']['cache_hit'])
            # Alpha.4 partitioned resolver: a body-only Python edit with no outbound parser facts
            # does not dirty the built-in relation partitions either.
            self.assertTrue(out['project_semantics']['base-resolver']['cache_hit'])

    def test_source_watcher_admits_external_edit_via_targeted_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); f=p/'a.py'
            f.write_text('def f():\n    return 1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            old=ws.revision
            ws.watch_start(0.05)
            f.write_text('def f():\n    return 2\n')
            result=ws.watch_wait(2.0)
            self.assertIn('a.py',result['candidate_paths'])
            self.assertEqual(result['refresh']['refresh_mode'],'targeted')
            self.assertEqual(result['refresh']['hashed_files'],1)
            self.assertNotEqual(ws.revision,old)
            events=ws.events_poll(0,reconcile=False)['events']
            self.assertTrue(any(e['kind']=='watch-observation' for e in events))
            ws.watch_stop()

    def test_metadata_preserving_edit_is_caught_by_deep_integrity_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); f=p/'a.py'
            f.write_text('value = 1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            st=f.stat(); old=ws.revision
            # Alpha.8 strengthens ordinary perception integrity: ctime/inode are part of the
            # admitted source fingerprint, so same-size + restored-mtime drift is detected before
            # cognition continues. Deep refresh remains the cryptographic fallback.
            f.write_text('value = 2\n')
            os.utime(f, ns=(st.st_atime_ns,st.st_mtime_ns))
            quick=ws.reconcile()
            self.assertFalse(quick['unchanged'])
            self.assertEqual(quick['hashed_files'],1)
            self.assertEqual(quick['changed_paths'],['a.py'])
            self.assertNotEqual(ws.revision,old)

    def test_targeted_refresh_rejects_escape_path(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('x=1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            with self.assertRaises(ValueError):
                ws.refresh_paths(['../outside.py'])

    @unittest.skipUnless(TypeScriptCompilerProvider().available()[0] and BrowserRuntime.probe().get('available'), 'TS/browser unavailable')
    def test_runtime_element_maps_to_unique_jsx_owner(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'index.html').write_text('<!doctype html><button id="save">Save</button>')
            (p/'App.tsx').write_text('export function App(){ return <button id="save">Save</button> }\n')
            ws=HabitatWorkspace.create(p,root/'h')
            obs=ws.open_ui_runtime('index.html')
            button=next(e for e in obs['elements'] if e['attrs'].get('id')=='save')
            hints=button.get('source_hints',[])
            jsx=[h for h in hints if h['relation']=='framework-jsx-anchor']
            owners=[h for h in hints if h['relation']=='framework-render-owner']
            self.assertEqual(len(jsx),1,hints)
            self.assertEqual(jsx[0]['path'],'App.tsx')
            self.assertEqual(jsx[0]['trust'],'parser')
            self.assertTrue(any(h['path']=='App.tsx' for h in owners),hints)
            ws.close()

    @unittest.skipUnless(TypeScriptCompilerProvider().available()[0] and BrowserRuntime.probe().get('available'), 'TS/browser unavailable')
    def test_duplicate_jsx_anchor_is_not_promoted_to_unique_ownership(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'index.html').write_text('<button id="save">Save</button>')
            (p/'A.tsx').write_text('export function A(){ return <button id="save">A</button> }\n')
            (p/'B.tsx').write_text('export function B(){ return <button id="save">B</button> }\n')
            ws=HabitatWorkspace.create(p,root/'h')
            obs=ws.open_ui_runtime('index.html')
            button=next(e for e in obs['elements'] if e['attrs'].get('id')=='save')
            jsx=[h for h in button.get('source_hints',[]) if h['relation']=='framework-jsx-anchor']
            self.assertEqual(len(jsx),2,jsx)
            self.assertTrue(all(h['trust']=='heuristic' for h in jsx),jsx)
            ws.close()

    def test_context_refresh_returns_revision_bound_delta(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            f=p/'auth.py'; f.write_text('def validate(value):\n    return value == "ok"\n')
            (p/'service.py').write_text('import auth\ndef login(v):\n    return auth.validate(v)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            ctx=ws.orient('fix login validation',budget=6)
            old_handle=ctx.handle; old_revision=ctx.revision
            f.write_text('def validate(value):\n    return value in {"ok","better"}\n')
            refreshed=ws.context_refresh(old_handle)
            self.assertEqual(refreshed['previous_revision'],old_revision)
            self.assertNotEqual(refreshed['current_revision'],old_revision)
            self.assertIn('auth.py',refreshed['delta']['changed_paths'])
            self.assertNotEqual(refreshed['context']['handle'],old_handle)
            self.assertTrue(refreshed['delta']['retained_object_ids'])

    def test_context_materializer_is_bounded_and_symbol_oriented(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def validate_credentials(email,password):\n    return password == "secret"\n' + ('# filler\n'*200))
            (p/'service.py').write_text('import auth\ndef login(e,p):\n    return auth.validate_credentials(e,p)\n')
            ws=HabitatWorkspace.create(p,root/'h')
            ctx=ws.orient('fix credential validation login',budget=6)
            packet=ws.context_materialize(ctx.handle,max_source_bytes=120,max_objects=6)
            self.assertFalse(packet['stale'])
            self.assertLessEqual(packet['source_bytes'],120)
            self.assertTrue(any(o.get('source_authority')=='exact-source' for o in packet['objects']))
            self.assertTrue(all(not (o.get('kind') is None and 'source' in o) for o in packet['objects']))
            # Materialization must never dump the entire filler-heavy source file through a file object.
            self.assertNotIn('# filler\n# filler\n# filler',json.dumps(packet))

    def test_context_materializer_refuses_stale_handle(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); f=p/'a.py'
            f.write_text('def f():\n    return 1\n')
            ws=HabitatWorkspace.create(p,root/'h'); ctx=ws.orient('fix function f',budget=4)
            f.write_text('def f():\n    return 2\n')
            packet=ws.context_materialize(ctx.handle,max_source_bytes=1000)
            self.assertTrue(packet['stale'])
            self.assertEqual(packet['objects'],[])

    def test_protocol_exposes_watcher_without_generic_shell(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('x=1\n')
            ws=HabitatWorkspace.create(p,root/'h')
            caps=HabitatProtocol(ws).handle({'id':'1','method':'protocol.capabilities','params':{}})['result']
            self.assertIn('workspace.watch.wait',caps['methods'])
            self.assertFalse(caps['generic_shell'])


if __name__ == '__main__':
    unittest.main()

import json
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.semantic.typescript import TypeScriptCompilerProvider
from habitat.ui import BrowserRuntime
from .support import WorkspaceTemporaryDirectory


class Alpha4AgentResidencyTests(unittest.TestCase):
    def test_body_only_target_edit_keeps_relation_partitions_clean(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            a=p/'a.py'; a.write_text('def work():\n    return 1\n')
            (p/'b.py').write_text('from a import work\ndef run():\n    return work()\n')
            ws=td.create_workspace(p,root/'h'); ws.refresh('settle')
            a.write_text('def work():\n    return 2\n')
            out=ws.reconcile(); base=out['project_semantics']['base-resolver']
            self.assertEqual(out['compiled_files'],1)
            self.assertEqual(base['partitions_recomputed'],0,base)
            self.assertTrue(base['cache_hit'])
            self.assertEqual(base['dirty_paths'],[])

    def test_body_only_edit_with_same_outbound_facts_reuses_own_partition(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def work():\n    return 1\n')
            b=p/'b.py'; b.write_text('from a import work\ndef run():\n    value = 1\n    return work()\n')
            ws=td.create_workspace(p,root/'h'); ws.refresh('settle')
            b.write_text('from a import work\ndef run():\n    value = 2\n    return work()\n')
            out=ws.reconcile(); base=out['project_semantics']['base-resolver']
            self.assertEqual(out['compiled_files'],1)
            self.assertEqual(base['partitions_recomputed'],0,base)
            self.assertTrue(base['cache_hit'])

    def test_resolution_surface_change_invalidates_reverse_partition(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def work():\n    return 1\n')
            (p/'b.py').write_text('def run():\n    return work()\n')
            ws=td.create_workspace(p,root/'h'); ws.refresh('settle')
            (p/'c.py').write_text('def work():\n    return 3\n')
            out=ws.reconcile(); base=out['project_semantics']['base-resolver']
            self.assertEqual(out['compiled_files'],1)
            self.assertIn('b.py',base['dirty_paths'],base)
            self.assertGreaterEqual(base['partitions_recomputed'],1)
            run=next(x for x in ws.store.all_symbols() if x['path']=='b.py' and x['name']=='run')
            calls=[r for r in ws.store.relations_for(run['id']) if r['source_id']==run['id'] and r['kind']=='calls']
            self.assertEqual(len(calls),2,calls)
            self.assertTrue(all(r['trust']=='heuristic' for r in calls),calls)

    def test_residency_evicts_unpinned_by_capacity_and_keeps_pin(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n\ndef gamma():\n    return beta()\n')
            ws=td.create_workspace(p,root/'h')
            ctx=ws.orient('change alpha beta gamma',budget=6)
            ws.residency_configure(max_objects=2,max_source_bytes=10000)
            result=ws.residency_admit(ctx.handle,pin_top=1)
            status=result['status']
            self.assertEqual(status['count'],2,status)
            self.assertEqual(sum(1 for x in status['objects'] if x['pinned']),1,status)
            pinned=next(x['object_id'] for x in status['objects'] if x['pinned'])
            self.assertIn(pinned,[o.object_id for o in ctx.objects])
            self.assertTrue(all('source' not in dict(r) for r in ws.store.resident_rows()))

    def test_residency_detects_stale_source_without_copying_source(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); f=p/'a.py'
            f.write_text('def alpha():\n    return 1\n')
            ws=td.create_workspace(p,root/'h'); ctx=ws.orient('change alpha',budget=4)
            ws.residency_admit(ctx.handle)
            before=ws.residency_status(); self.assertGreater(before['state_counts']['fresh'],0)
            f.write_text('def alpha():\n    return 2\n')
            status=ws.residency_status()
            self.assertEqual(status['state_counts']['stale'],before['state_counts']['fresh'],status)
            packet=ws.residency_materialize()
            self.assertEqual(packet['objects'],[])
            self.assertTrue(all(x['reason']=='stale' for x in packet['omissions']),packet)

    def test_residency_materializes_exact_source_and_touches_access_state(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def alpha():\n    return 123\n')
            ws=td.create_workspace(p,root/'h'); ctx=ws.orient('alpha implementation',budget=4)
            ws.residency_admit(ctx.handle)
            before=ws.residency_status()['objects'][0]['access_count']
            packet=ws.residency_materialize(max_source_bytes=5000,max_objects=4)
            self.assertTrue(any(o.get('source_authority')=='exact-source' for o in packet['objects']),packet)
            after=ws.residency_status()['objects'][0]['access_count']
            self.assertGreater(after,before)

    def test_fresh_residency_becomes_bounded_context_prior(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def validate_credentials(email,password):\n    return password == "secret"\n')
            (p/'billing.py').write_text('def calculate_tax(total):\n    return total * 0.1\n')
            ws=td.create_workspace(p,root/'h')
            first=ws.orient('fix credential validation',budget=4)
            ws.residency_admit(first.handle,pin_top=1)
            second=ws.orient('review credential validation logic',budget=4)
            self.assertTrue(any('resident' in o.lane for o in second.objects),[(o.object_id,o.lane) for o in second.objects])
            unrelated=ws.orient('calculate billing tax total',budget=4)
            auth_ids={o.object_id for o in first.objects if o.path=='auth.py'}
            resident_auth=[o for o in unrelated.objects if o.object_id in auth_ids and 'resident' in o.lane]
            self.assertEqual(resident_auth,[],[(o.path,o.lane,o.relevance) for o in unrelated.objects])

    def test_checkpoint_binds_residency_and_distinguishes_resume_modes(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def alpha():\n    return 1\n')
            other=p/'notes.md'; other.write_text('one\n')
            ws=td.create_workspace(p,root/'h'); ctx=ws.orient('alpha implementation',budget=4); ws.residency_admit(ctx.handle,pin_top=1)
            cp=ws.checkpoint('continue alpha',None,next_action='inspect alpha')
            self.assertTrue(cp['resident_objects']); self.assertIn('compiler_state_fingerprint',cp); self.assertIn('event_cursor',cp)
            direct=ws.resume(cp['id']); self.assertEqual(direct['resume_mode'],'direct',direct)
            other.write_text('two changed\n')
            selective=ws.resume(cp['id']); self.assertEqual(selective['resume_mode'],'selective-revalidate',selective)
            (p/'auth.py').write_text('def alpha():\n    return 2\n')
            reorient=ws.resume(cp['id']); self.assertEqual(reorient['resume_mode'],'reorient',reorient)
            self.assertTrue(reorient['stale_objects'])

    def test_protocol_trace_measures_calls_and_exact_source_bytes(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def alpha():\n    return 123\n')
            ws=td.create_workspace(p,root/'h'); proto=HabitatProtocol(ws)
            start=proto.handle({'id':'s','method':'workspace.trace.start','params':{'label':'probe'}})
            self.assertTrue(start['ok']); tid=start['result']['trace_id']
            orient=proto.handle({'id':'o','method':'workspace.orient','params':{'task':'alpha implementation','budget':4}})
            handle=orient['result']['handle']
            mat=proto.handle({'id':'m','method':'workspace.context.materialize','params':{'handle':handle,'max_source_bytes':5000}})
            self.assertTrue(mat['ok'])
            stop=proto.handle({'id':'x','method':'workspace.trace.stop','params':{'trace_id':tid}})['result']
            self.assertEqual(stop['call_count'],2,stop)
            self.assertEqual(stop['methods'].get('workspace.orient'),1)
            self.assertEqual(stop['methods'].get('workspace.context.materialize'),1)
            self.assertGreater(stop['response_bytes'],0)
            self.assertGreater(stop['exact_source_bytes'],0,stop)

    def test_protocol_exposes_alpha4_residency_and_trace_without_shell(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('x=1\n')
            ws=td.create_workspace(p,root/'h')
            caps=HabitatProtocol(ws).handle({'id':'1','method':'protocol.capabilities','params':{}})['result']
            self.assertIn('workspace.context.residency.admit',caps['methods'])
            self.assertIn('workspace.trace.start',caps['methods'])
            self.assertFalse(caps['generic_shell'])



    def test_specific_task_does_not_fill_context_with_unrelated_generic_symbols(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'auth.py').write_text('def validate_credentials(email,password):\n    return password == "secret"\n')
            for i in range(20):
                (p/f'noise_{i:02d}.py').write_text(f'def helper_{i}(value):\n    return value\n')
            ws=td.create_workspace(p,root/'h')
            ctx=ws.orient('fix credential validation login',budget=8)
            noise=[o for o in ctx.objects if o.path.startswith('noise_')]
            self.assertEqual(noise,[],[(o.path,o.lane,o.reason) for o in noise])
            self.assertTrue(any(o.path=='auth.py' for o in ctx.objects),[(o.path,o.lane) for o in ctx.objects])

    def test_pinned_residency_reports_overcommit_instead_of_evicting_pin(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'a.py').write_text('def alpha():\n    return 1\n\ndef beta():\n    return 2\n')
            ws=td.create_workspace(p,root/'h')
            ctx=ws.orient('alpha beta implementation',budget=4)
            ws.residency_configure(max_objects=2,max_source_bytes=10000)
            admitted=ws.residency_admit(ctx.handle,pin_top=2,max_admit=2)
            self.assertEqual(sum(1 for x in admitted['status']['objects'] if x['pinned']),2)
            cap=ws.residency_configure(max_objects=1,max_source_bytes=10000)
            self.assertTrue(cap['overcommitted'],cap)
            self.assertEqual(cap['overcommit_reason'],'pinned residents exceed capacity')
            status=ws.residency_status()
            self.assertEqual(status['count'],2,status)
            self.assertTrue(all(x['pinned'] for x in status['objects']))

    def test_trace_telemetry_failure_never_changes_agent_result(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('def alpha():\n    return 1\n')
            ws=td.create_workspace(p,root/'h'); proto=HabitatProtocol(ws)
            ws.record_trace_call=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('telemetry failure'))
            result=proto.handle({'id':'q','method':'workspace.query','params':{'query':'alpha','limit':4}})
            self.assertTrue(result['ok'],result)
            self.assertTrue(result['result'])

    def test_protocol_rejects_invalid_optional_alpha4_parameter_types(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('x=1\n')
            ws=td.create_workspace(p,root/'h'); proto=HabitatProtocol(ws)
            bad_evict=proto.handle({'id':'e','method':'workspace.context.residency.evict','params':{'object_ids':'not-a-list'}})
            self.assertFalse(bad_evict['ok']); self.assertEqual(bad_evict['error']['code'],'INVALID_PARAMS')
            bad_checkpoint=proto.handle({'id':'c','method':'workspace.checkpoint','params':{'task':'continue','resident_object_ids':'bad'}})
            self.assertFalse(bad_checkpoint['ok']); self.assertEqual(bad_checkpoint['error']['code'],'INVALID_PARAMS')
            bad_trace=proto.handle({'id':'t','method':'workspace.trace.status','params':{'trace_id':123}})
            self.assertFalse(bad_trace['ok']); self.assertEqual(bad_trace['error']['code'],'INVALID_PARAMS')

    @unittest.skipUnless(TypeScriptCompilerProvider().available()[0] and BrowserRuntime.probe().get('available'), 'TS/browser unavailable')
    def test_runtime_ui_maps_unique_jsx_event_handler(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir()
            (p/'index.html').write_text('<!doctype html><button id="save">Save</button>')
            (p/'App.tsx').write_text('''export function App(){\n  function handleSave(){ return 1 }\n  return <button id="save" onClick={handleSave}>Save</button>\n}\n''')
            ws=td.create_workspace(p,root/'h')
            obs=ws.open_ui_runtime('index.html')
            button=next(e for e in obs['elements'] if e['attrs'].get('id')=='save')
            handlers=[h for h in button.get('source_hints',[]) if h['relation']=='framework-event-handler:click']
            self.assertEqual(len(handlers),1,button.get('source_hints'))
            self.assertEqual(handlers[0]['path'],'App.tsx')
            self.assertEqual(handlers[0]['trust'],'parser')
            ws.close()


if __name__ == '__main__':
    unittest.main()

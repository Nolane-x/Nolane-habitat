from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from habitat.mcp_adapter import tool_catalog
from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace


class Alpha11ObservatoryRuntimeTests(unittest.TestCase):
    def make_ws(self, files: dict[str,str] | None = None):
        td=tempfile.TemporaryDirectory(); base=Path(td.name); root=base/'project'; root.mkdir(); hab=base/'habitat'
        for rel,text in (files or {'auth.py':'def validate(user):\n    return bool(user)\n'}).items():
            p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')
        ws=HabitatWorkspace.create(root,hab); self.addCleanup(ws.close); self.addCleanup(td.cleanup)
        return ws,root,hab

    def test_observatory_http_is_read_only_and_cross_thread_safe(self):
        ws,_,_=self.make_ws(); aid=ws.agent_open('Codex',{'surface':'test'})['id']
        ctx=ws.orient('validate user',agent_id=aid); ep=ws.episode_start('validate user',ctx.handle)
        ws.hypothesis_create('validation rejects missing user',episode_id=ep['id'])
        obs=ws.observatory_start(open_browser=False); self.addCleanup(ws.observatory_stop)
        health=json.loads(urllib.request.urlopen(obs['url']+'api/health',timeout=3).read())
        self.assertTrue(health['read_only']); self.assertEqual(health['revision'],ws.revision)
        snap=json.loads(urllib.request.urlopen(obs['url']+'api/snapshot',timeout=3).read())
        self.assertTrue(snap['read_only']); self.assertEqual(snap['agents'][0]['name'],'Codex')
        req=urllib.request.Request(obs['url']+'api/snapshot',method='POST')
        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req,timeout=3)
        self.assertEqual(cm.exception.code,405)
        self.assertEqual(json.loads(cm.exception.read())['error'],'observer-read-only')

    def test_domain_activity_events_capture_agent_episode_mutation_and_are_monotonic(self):
        ws,_,_=self.make_ws(); a=ws.agent_open('Claude')['id']; ctx=ws.orient('change validate',agent_id=a); ep=ws.episode_start('change validate',ctx.handle)
        tx=ws.stage_change([{'op':'replace_text','path':'auth.py','old':'bool(user)','new':'user is not None'}],episode_id=ep['id'],agent_id=a)
        ws.commit_change(tx['id'],a); ws.episode_finish(ep['id'])
        ev=ws.activity_since(0,200)['events']; seq=[x['seq'] for x in ev]
        self.assertEqual(seq,sorted(seq)); kinds={x['kind'] for x in ev}
        for expected in {'agent.connected','episode.started','transaction.staged','transaction.committed','episode.finished'}: self.assertIn(expected,kinds)

    def test_runtime_twin_links_otel_and_dap_observation_to_source_symbol(self):
        ws,root,_=self.make_ws(); aid=ws.agent_open('runtime-agent')['id']
        out=ws.runtime_ingest('opentelemetry',[{'trace_id':'t1','span_id':'s1','name':'validate call','status':{'code':'OK'},'attributes':{'code.file.path':str(root/'auth.py'),'code.line.number':1,'http.route':'/login'},'duration_ms':2.4}],agent_id=aid)
        self.assertEqual(out['ingested'],1); self.assertEqual(out['events'][0]['path'],'auth.py'); self.assertIsNotNone(out['events'][0]['symbol_id'])
        dap=ws.runtime_ingest('dap',[{'seq':7,'type':'event','event':'stopped','body':{'threadId':1,'source':{'path':str(root/'auth.py')},'line':1}}],agent_id=aid)
        self.assertEqual(dap['events'][0]['source'],'dap'); self.assertEqual(dap['events'][0]['path'],'auth.py')
        self.assertGreaterEqual(len(ws.runtime_timeline(agent_id=aid)['events']),2)

    def test_epistemic_runtime_prioritizes_contradiction_and_never_calls_it_chain_of_thought(self):
        ws,_,_=self.make_ws(); aid=ws.agent_open('A')['id']; ep=ws.episode_start('debug auth')
        ws.epistemic_create('unknown','whether cache is stale',agent_id=aid,episode_id=ep['id'])
        c=ws.epistemic_create('contradiction','test says allowed while runtime says denied',agent_id=aid,episode_id=ep['id'])
        nxt=ws.cognition_next(aid,ep['id'])
        self.assertEqual(nxt['next']['operation'],'discriminate-contradiction'); self.assertEqual(nxt['next']['ref_id'],c['id'])
        self.assertIn('not hidden model chain-of-thought',nxt['claim_boundary'])
        probe=ws.cognition_probe_unknowns(aid); self.assertIn('not exhaustive',probe['claim_boundary'])

    def test_semantic_fabric_is_fail_honest_provider_capability_surface(self):
        ws,_,_=self.make_ws(); report=ws.semantic_fabric()
        self.assertEqual(report['fabric_version'],1); self.assertIn('providers',report)
        self.assertIn('not claimed active',report['claim_boundary'])
        for p in report['providers']:
            self.assertIn(p['precision'],{'parser','semantic'})
            if not p['available']: self.assertTrue(p['reason'])

    def test_protocol_exposes_observatory_runtime_epistemic_and_fabric_surfaces(self):
        ws,_,_=self.make_ws(); methods=set(HabitatProtocol(ws).METHODS)
        expected={'workspace.semantic.fabric','workspace.activity.since','workspace.observatory.start','workspace.observatory.status','workspace.epistemic.create','workspace.epistemic.state','workspace.cognition.next','workspace.cognition.probe_unknowns','workspace.runtime.ingest','workspace.runtime.timeline'}
        self.assertTrue(expected.issubset(methods))

    def test_mcp_surface_remains_compact_and_start_task_is_identity_minting_entry(self):
        tools=tool_catalog(); names=[x['name'] for x in tools]
        self.assertEqual(len(tools),12); self.assertIn('habitat_start_task',names); self.assertNotIn('habitat_attach',names)

    def test_workspace_manifest_declares_observer_only_autostart_contract(self):
        ws,_,_=self.make_ws(); obs=ws.manifest['observatory']
        self.assertEqual(obs['mode'],'observer-only'); self.assertTrue(obs['auto_start_on_agent_server']); self.assertFalse(obs['control_actions'])
        self.assertIn('raw private',obs['reasoning_surface'])

    def test_project_memory_is_provenance_bound_agent_isolated_and_supersedable(self):
        ws,root,_=self.make_ws(); a=ws.agent_open('A')['id']; b=ws.agent_open('B')['id']
        shared=ws.memory_record('semantic','validation entrypoint is auth.validate',provenance={'source':'semantic-twin'})
        private=ws.memory_record('failure','retrying the old patch repeated the regression',agent_id=a,confidence=0.7,provenance={'source':'episode-review'})
        self.assertIn(shared['id'],{x['id'] for x in ws.memory_recall('validation',agent_id=b)['memories']})
        self.assertNotIn(private['id'],{x['id'] for x in ws.memory_recall('regression',agent_id=b)['memories']})
        self.assertIn(private['id'],{x['id'] for x in ws.memory_recall('regression',agent_id=a)['memories']})
        newer=ws.memory_record('semantic','validation entrypoint moved to auth.verify',supersedes=shared['id'])
        self.assertEqual(ws.memory_status(shared['id'])['status'],'superseded'); self.assertEqual(ws.memory_status(shared['id'])['invalidated_by'],newer['id'])
        (root/'auth.py').write_text('def validate(user):\n    return user is not None\n',encoding='utf-8'); ws.refresh_paths(['auth.py'],reason='memory-drift-probe')
        self.assertTrue(ws.memory_status(newer['id'])['revision_drift'])
        inv=ws.memory_invalidate(newer['id'],'new evidence contradicted this memory'); self.assertEqual(inv['status'],'invalidated')
        self.assertIn('not canonical source truth',inv['claim_boundary'])

    def test_protocol_exposes_project_memory_and_otel_log_metric_runtime(self):
        ws,root,_=self.make_ws(); a=ws.agent_open('A')['id']; proto=HabitatProtocol(ws); methods=set(proto.METHODS)
        self.assertTrue({'workspace.memory.record','workspace.memory.status','workspace.memory.recall','workspace.memory.invalidate'}.issubset(methods))
        rec=proto.handle({'id':'m1','method':'workspace.memory.record','params':{'kind':'decision','statement':'prefer targeted verification','agent_id':a}})
        self.assertTrue(rec['ok']); mid=rec['result']['id']
        recalled=proto.handle({'id':'m2','method':'workspace.memory.recall','params':{'query':'targeted verification','agent_id':a}})
        self.assertTrue(recalled['ok']); self.assertEqual(recalled['result']['memories'][0]['id'],mid)
        out=ws.runtime_ingest('opentelemetry',[
            {'record_type':'log','severity_text':'WARN','body':'claim cache stale','attributes':{'code.file.path':str(root/'auth.py'),'code.line.number':1}},
            {'record_type':'metric','metric_name':'auth.cache.miss','value':3,'unit':'1'}],agent_id=a)
        self.assertEqual([e['kind'] for e in out['events']],['log','metric']); self.assertEqual(out['events'][0]['path'],'auth.py')
        self.assertEqual(out['events'][1]['attributes']['otel.metric.value'],3)

    def test_observatory_snapshot_includes_project_memory_without_human_control(self):
        ws,_,_=self.make_ws(); ws.memory_record('decision','keep observer plane read only',provenance={'source':'architecture'})
        obs=ws.observatory_start(open_browser=False); self.addCleanup(ws.observatory_stop)
        snap=json.loads(urllib.request.urlopen(obs['url']+'api/snapshot',timeout=3).read())
        self.assertTrue(any(x['statement']=='keep observer plane read only' for x in snap['project_memory']))
        self.assertTrue(snap['read_only'])

    def test_observatory_assets_are_packaged_source_and_release_identity_is_consistent(self):
        import habitat, tomllib, re
        base=Path(__file__).parents[1]
        self.assertTrue((base/'habitat'/'observatory_assets'/'index.html').is_file()); self.assertTrue((base/'habitat'/'observatory_assets'/'app.js').is_file())
        version=(base/'VERSION').read_text().strip(); self.assertEqual(habitat.__version__,version)
        meta=tomllib.loads((base/'pyproject.toml').read_text())
        m=re.fullmatch(r'(\d+\.\d+\.\d+)-alpha\.(\d+)',version); self.assertIsNotNone(m)
        self.assertEqual(meta['project']['version'],f"{m.group(1)}a{m.group(2)}")


if __name__=='__main__': unittest.main()

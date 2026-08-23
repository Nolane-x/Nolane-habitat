from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import habitat
from habitat.workspace import HabitatWorkspace
from habitat.mutation import TransactionConflict


class Alpha13MicroDepthTests(unittest.TestCase):
    def make_ws(self):
        td=tempfile.TemporaryDirectory(); base=Path(td.name); project=base/'project'; project.mkdir()
        (project/'app.py').write_text('def f(x):\n    return x + 1\n',encoding='utf-8')
        (project/'tests').mkdir(); (project/'tests'/'test_app.py').write_text('from app import f\n\ndef test_f():\n    assert f(1) == 2\n',encoding='utf-8')
        ws=HabitatWorkspace.create(project,base/'habitat')
        self.addCleanup(td.cleanup)
        self.addCleanup(ws.close)
        return td,project,ws

    def test_release_identity_current(self):
        base=Path(__file__).resolve().parents[1]
        self.assertEqual((base/'VERSION').read_text().strip(),'0.1.0-alpha.19')
        self.assertEqual(habitat.__version__,'0.1.0-alpha.19')
        self.assertIn('version = "0.1.0a19"',(base/'pyproject.toml').read_text())

    def test_memory_exact_echo_same_revision_is_suppressed(self):
        td,project,ws=self.make_ws()
        try:
            first=ws.memory_record('semantic','f increments its argument')
            second=ws.memory_record('semantic','f increments its argument')
            self.assertEqual(first['id'],second['id'])
            self.assertTrue(second['deduplicated_echo'])
            rows=ws.store.conn.execute("SELECT COUNT(*) FROM project_memories WHERE status='active'").fetchone()[0]
            self.assertEqual(rows,1)
        finally: ws.close();td.cleanup()

    def test_runtime_duplicate_is_idempotent_but_conflicting_collision_fails(self):
        td,project,ws=self.make_ws()
        try:
            record={'trace_id':'t','span_id':'s','name':'call','started_at':'2026-01-01T00:00:00Z','attributes':{'service.name':'api'}}
            one=ws.runtime_ingest('opentelemetry',[record]); two=ws.runtime_ingest('opentelemetry',[record])
            self.assertEqual(one['ingested'],1); self.assertEqual(two['ingested'],0)
            conflict={**record,'attributes':{'service.name':'other'}}
            with self.assertRaises(TransactionConflict): ws.runtime_ingest('opentelemetry',[conflict])
        finally: ws.close();td.cleanup()

    def test_counterfactual_verification_becomes_stale_after_overlay_change(self):
        td,project,ws=self.make_ws()
        try:
            w=ws.counterfactual_fork('alt')
            ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'app.py','old':'x + 1','new':'x + 2'}])
            verified=ws.counterfactual_verify(w['id'])
            self.assertEqual(verified['overlay_generation'],1)
            self.assertTrue(ws.counterfactual_status(w['id'])['verification_fresh'])
            ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'app.py','old':'x + 2','new':'x + 3'}])
            st=ws.counterfactual_status(w['id']); self.assertEqual(st['verification_status'],'stale'); self.assertFalse(st['verification_fresh'])
            with self.assertRaises(TransactionConflict): ws.counterfactual_promote(w['id'])
        finally: ws.close();td.cleanup()

    def test_context_efficiency_exposes_refetch_and_io_amplification(self):
        td,project,ws=self.make_ws()
        try:
            ctx=ws.orient('increment function f')
            space=ws.context_address_space(ctx.handle,100)
            page=next(p for p in space['pages'] if p.get('fetchable'))
            ws.context_fetch_pages(ctx.handle,[page['page_id']]); ws.context_fetch_pages(ctx.handle,[page['page_id']])
            eff=ws.context_efficiency(ctx.handle)
            self.assertGreaterEqual(eff['duplicate_page_faults'],1)
            self.assertGreater(eff['refetch_ratio'],0)
            self.assertIsNotNone(eff['authority_io_amplification'])
        finally: ws.close();td.cleanup()

    def test_cognitive_loop_health_detects_visible_repetition(self):
        td,project,ws=self.make_ws()
        try:
            aid=ws.agent_open('loop-agent')['id']
            for _ in range(18): ws.activity_emit('tool.started','cognition',agent_id=aid,ref_id='same-tool',status='running',summary='same operation')
            health=ws.cognition_health(aid)
            self.assertIn(health['loop']['risk'],{'medium','high'})
            plan=ws.cognition_plan(aid)
            self.assertTrue(any(x['operation']=='break-cognitive-loop' for x in plan['operations']))
        finally: ws.close();td.cleanup()

    def test_unknown_probe_surfaces_high_invariant_without_verifier(self):
        td,project,ws=self.make_ws()
        try:
            ws.invariant_create('Authentication must never bypass authorization',severity='error')
            probes=ws.cognition_probe_unknowns()['probes']
            self.assertIn('critical-invariant-verifier-gap',{p['code'] for p in probes})
        finally: ws.close();td.cleanup()

    def test_observatory_snapshot_consistent_and_assets_single_response(self):
        td,project,ws=self.make_ws(); obs=None
        try:
            obs=ws.observatory_start(port=0,open_browser=False)
            host='127.0.0.1'; port=obs['port']
            conn=http.client.HTTPConnection(host,port,timeout=5); conn.request('GET','/app.js'); r=conn.getresponse(); data=r.read(); conn.close()
            self.assertEqual(r.status,200); self.assertEqual(int(r.getheader('Content-Length')),len(data)); self.assertNotIn(b'HTTP/1.',data)
            conn=http.client.HTTPConnection(host,port,timeout=5); conn.request('GET','/api/snapshot'); sr=conn.getresponse(); snap=json.loads(sr.read()); conn.close()
            self.assertEqual(snap['observer_health']['snapshot_consistency'],'sqlite-read-transaction')
            self.assertIn('activity_loop',snap['observer_health'])
        finally:
            if obs: ws.observatory_stop()
            ws.close();td.cleanup()

    def test_activity_api_reports_bounds_and_more(self):
        td,project,ws=self.make_ws()
        try:
            for i in range(5): ws.activity_emit('probe.event','test',summary=str(i))
            out=ws.activity_since(0,2)
            self.assertEqual(len(out['events']),2); self.assertTrue(out['has_more']); self.assertGreaterEqual(out['latest_seq'],out['last_returned_seq'])
            self.assertIn('gap_detected',out)
        finally: ws.close();td.cleanup()

    def test_invariant_verifier_link_clears_verifier_gap(self):
        td,project,ws=self.make_ws()
        try:
            inv=ws.invariant_create('Authentication path must be verified',severity='error')
            before=ws.cognition_health()
            self.assertGreaterEqual(before['epistemic_pressure']['unverified_critical_invariants'],1)
            ws.invariant_link(inv['id'],'test','tests/test_app.py',relation='verifier')
            st=ws.invariant_status(inv['id'])
            self.assertEqual(st['verifier_count'],1)
            after=ws.cognition_health()
            self.assertEqual(after['epistemic_pressure']['unverified_critical_invariants'],0)
            codes={p['code'] for p in ws.cognition_probe_unknowns()['probes']}
            self.assertNotIn('critical-invariant-verifier-gap',codes)
        finally: ws.close();td.cleanup()

    def test_memory_same_statement_new_revision_preserves_history(self):
        td,project,ws=self.make_ws()
        try:
            first=ws.memory_record('semantic','f increments its argument')
            (project/'app.py').write_text('def f(x):\n    return x + 2\n',encoding='utf-8')
            ws.refresh()
            second=ws.memory_record('semantic','f increments its argument')
            self.assertNotEqual(first['id'],second['id'])
            self.assertNotEqual(first['base_revision'],second['base_revision'])
            self.assertFalse(bool(second.get('deduplicated_echo')))
        finally: ws.close();td.cleanup()

    def test_runtime_telemetry_redacts_sensitive_content_and_bounds_large_values(self):
        td,project,ws=self.make_ws()
        try:
            rec={
                'trace_id':'secret-trace','span_id':'s1','name':'genai-call','started_at':'2026-01-01T00:00:00Z',
                'attributes':{
                    'gen_ai.prompt':'tell me password=SUPERSECRET',
                    'api_key':'sk-live-secret',
                    'safe.attr':'ok',
                    'huge':'x'*5000,
                    'nested':{'access_token':'ABCDEF','keep':'visible'},
                }
            }
            out=ws.runtime_ingest('opentelemetry',[rec]); self.assertEqual(out['ingested'],1)
            row=ws.store.runtime_event(out['events'][0]['id'])
            attrs=json.loads(row['attributes_json'])
            blob=json.dumps(attrs)
            self.assertNotIn('SUPERSECRET',blob); self.assertNotIn('sk-live-secret',blob); self.assertNotIn('ABCDEF',blob)
            self.assertEqual(attrs['gen_ai.prompt'],'[REDACTED_BY_HABITAT]')
            self.assertEqual(attrs['api_key'],'[REDACTED_BY_HABITAT]')
            self.assertIn('[TRUNCATED]',attrs['huge'])
            self.assertGreaterEqual(attrs.get('habitat.telemetry.redacted_count',0),3)
            # DAP bodies are sanitized before durable persistence too.
            dap={'seq':7,'type':'event','event':'output','body':{'output':'password=TOPSECRET','variables':[{'name':'token','value':'ABC'}]}}
            d=ws.runtime_ingest('dap',[dap]); drow=ws.store.runtime_event(d['events'][0]['id']); dblob=drow['attributes_json']
            self.assertNotIn('TOPSECRET',dblob)
        finally: ws.close();td.cleanup()

    def test_runtime_duplicate_does_not_emit_second_observed_activity(self):
        td,project,ws=self.make_ws()
        try:
            record={'trace_id':'t','span_id':'same','name':'call','started_at':'2026-01-01T00:00:00Z','attributes':{'service.name':'api'}}
            ws.runtime_ingest('opentelemetry',[record])
            before=ws.store.conn.execute("SELECT COUNT(*) FROM activity_events WHERE kind='runtime.observed'").fetchone()[0]
            ws.runtime_ingest('opentelemetry',[record])
            after=ws.store.conn.execute("SELECT COUNT(*) FROM activity_events WHERE kind='runtime.observed'").fetchone()[0]
            self.assertEqual(before,after)
        finally: ws.close();td.cleanup()

    def test_fresh_counterfactual_verification_can_promote(self):
        td,project,ws=self.make_ws()
        try:
            w=ws.counterfactual_fork('fresh')
            ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'app.py','old':'return x + 1','new':'return x + 1  # verified candidate'}])
            verified=ws.counterfactual_verify(w['id'])
            self.assertEqual(verified['status'],'passed')
            self.assertTrue(ws.counterfactual_status(w['id'])['verification_fresh'])
            promoted=ws.counterfactual_promote(w['id'])
            self.assertEqual(promoted['world']['status'],'promoted')
        finally: ws.close();td.cleanup()

    def test_world_health_surfaces_stale_counterfactual_and_context_thrash(self):
        td,project,ws=self.make_ws()
        try:
            ctx=ws.orient('increment function f'); page=next(p for p in ws.context_address_space(ctx.handle,100)['pages'] if p.get('fetchable'))
            for _ in range(3): ws.context_fetch_pages(ctx.handle,[page['page_id']])
            w=ws.counterfactual_fork('stale-health'); ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'app.py','old':'x + 1','new':'x + 2'}]); ws.counterfactual_verify(w['id'])
            ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'app.py','old':'x + 2','new':'x + 3'}])
            h=ws.world_health()
            kinds={b['kind'] for b in h['blockers']}
            self.assertIn('stale-counterfactual-verification',kinds)
            self.assertIn('context-thrash',kinds)
            from habitat.protocol import HabitatProtocol
            rsp=HabitatProtocol(ws).handle({'id':'h','method':'workspace.world.health','params':{}})
            self.assertTrue(rsp['ok']); self.assertEqual(rsp['result']['counterfactuals']['stale_verifications'],1)
        finally: ws.close();td.cleanup()

    def test_observatory_sse_resume_and_gap_detection(self):
        td,project,ws=self.make_ws(); obs=None
        try:
            for i in range(4): ws.activity_emit('resume.event','test',summary=str(i))
            obs=ws.observatory_start(port=0,open_browser=False); port=obs['port']
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            conn.request('GET','/events',headers={'Last-Event-ID':'2'})
            r=conn.getresponse(); self.assertEqual(r.status,200)
            lines=[]
            for _ in range(12):
                line=r.fp.readline().decode('utf-8','replace')
                lines.append(line)
                if line.startswith('id: 3'): break
            blob=''.join(lines); self.assertIn('event: hello',blob); self.assertIn('id: 3',blob)
            conn.close()
            # Simulate retention/compaction by removing old rows; an old cursor must be reported as a gap.
            ws.store.conn.execute('DELETE FROM activity_events WHERE seq < 4'); ws.store.conn.commit()
            gap=ws.activity_since(1,10); self.assertTrue(gap['gap_detected']); self.assertGreaterEqual(gap['oldest_seq'],4)
        finally:
            if obs: ws.observatory_stop()
            ws.close();td.cleanup()

    def test_observatory_read_frames_survive_concurrent_activity_writer(self):
        td,project,ws=self.make_ws(); obs=None
        try:
            obs=ws.observatory_start(port=0,open_browser=False); port=obs['port']; errors=[]
            def writer():
                writer_ws=None
                try:
                    writer_ws=HabitatWorkspace(ws.habitat_dir)
                    for i in range(80):
                        writer_ws.activity_emit('concurrent.event','test',summary=str(i)); time.sleep(.002)
                except Exception as exc: errors.append(exc)
                finally:
                    if writer_ws: writer_ws.close()
            th=threading.Thread(target=writer); th.start()
            seqs=[]
            for _ in range(18):
                conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5); conn.request('GET','/api/snapshot'); r=conn.getresponse(); snap=json.loads(r.read()); conn.close()
                self.assertEqual(r.status,200); self.assertEqual(snap['observer_health']['snapshot_consistency'],'sqlite-read-transaction')
                seqs.append(int(snap['activity_seq'])); self.assertLessEqual(int(snap['observer_health']['activity_seq']),int(snap['activity_seq']))
            th.join(5); self.assertFalse(errors); self.assertEqual(seqs,sorted(seqs))
        finally:
            if obs: ws.observatory_stop()
            ws.close();td.cleanup()

    def test_observatory_assets_use_adaptive_lod_and_disclose_bounded_view(self):
        base=Path(__file__).resolve().parents[1]; app=(base/'habitat'/'observatory_assets'/'app.js').read_text(encoding='utf-8'); html=(base/'habitat'/'observatory_assets'/'index.html').read_text(encoding='utf-8')
        self.assertIn('function compressGraph',app); self.assertNotIn('.slice(0,420)',app); self.assertIn("addEventListener('gap'",app)
        self.assertIn('agentTrails',app); self.assertIn('focusUntil',app); self.assertIn('id="lodTop"',html); self.assertIn('id="thrashTop"',html)
        td,project,ws=self.make_ws(); obs=None
        try:
            # Inflate symbol count beyond observer read-model limit without changing UI truth semantics.
            for i in range(130): (project/f'n{i}.py').write_text(f'def n{i}():\n    return {i}\n',encoding='utf-8')
            ws.refresh(); obs=ws.observatory_start(port=0,open_browser=False)
            conn=http.client.HTTPConnection('127.0.0.1',obs['port'],timeout=5); conn.request('GET','/api/snapshot'); r=conn.getresponse(); snap=json.loads(r.read()); conn.close()
            self.assertTrue(snap['graph_sampling']['bounded']); self.assertGreater(snap['graph_sampling']['source_totals']['symbols'],120)
            self.assertIn('omitted project state is disclosed',snap['graph_sampling']['claim_boundary'])
        finally:
            if obs: ws.observatory_stop()
            ws.close();td.cleanup()

    def test_effect_and_dataflow_runtime_support_is_revision_bound(self):
        td,project,ws=self.make_ws()
        try:
            ws.effect_refresh(['app.py']); ws.dataflow_refresh(['app.py'])
            ev={'trace_id':'corr','span_id':'s','name':'f runtime','started_at':'2026-01-01T00:00:00Z','attributes':{'code.file.path':'app.py','code.line.number':1}}
            ws.runtime_ingest('opentelemetry',[ev])
            effects=ws.effect_snapshot(path='app.py')['effects']; flows=ws.dataflow_snapshot(path='app.py')['flows']
            self.assertTrue(any(x['runtime_support']['observed'] for x in effects))
            self.assertTrue(any(x['runtime_support']['observed'] for x in flows))
            self.assertTrue(any(x['runtime_support']['grade']=='strong' for x in effects+flows))
            # A source revision invalidates runtime support rather than allowing stale observations to strengthen new static facts.
            (project/'app.py').write_text('def f(x):\n    y=x+1\n    return y\n',encoding='utf-8'); ws.refresh(); ws.effect_refresh(['app.py']); ws.dataflow_refresh(['app.py'])
            self.assertFalse(any(x['runtime_support']['observed'] for x in ws.effect_snapshot(path='app.py')['effects']))
        finally: ws.close();td.cleanup()

    def test_observatory_consistency_claim_distinguishes_sqlite_and_external_projection(self):
        td,project,ws=self.make_ws(); obs=None
        try:
            obs=ws.observatory_start(port=0,open_browser=False); conn=http.client.HTTPConnection('127.0.0.1',obs['port'],timeout=5); conn.request('GET','/api/snapshot'); r=conn.getresponse(); snap=json.loads(r.read()); conn.close()
            self.assertEqual(snap['observer_health']['snapshot_consistency'],'sqlite-read-transaction')
            self.assertEqual(snap['observer_health']['external_projection_consistency'],'revision-bound-best-effort')
            self.assertIn('filesystem projections',snap['claim_boundary'])
        finally:
            if obs: ws.observatory_stop()
            ws.close();td.cleanup()

    def test_failed_counterfactual_verification_blocks_promotion(self):
        td,project,ws=self.make_ws()
        try:
            w=ws.counterfactual_fork('bad'); ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'app.py','old':'x + 1','new':'x + 99'}])
            verified=ws.counterfactual_verify(w['id']); self.assertEqual(verified['status'],'failed'); self.assertTrue(ws.counterfactual_status(w['id'])['verification_fresh'])
            with self.assertRaises(TransactionConflict): ws.counterfactual_promote(w['id'])
            self.assertEqual(ws.world_health()['counterfactuals']['failed_verifications'],1)
        finally: ws.close();td.cleanup()

    def test_runtime_collision_compares_full_durable_provenance(self):
        td,project,ws=self.make_ws()
        try:
            rec={'trace_id':'t2','span_id':'s2','name':'call','status':'ok','started_at':'2026-01-01T00:00:00Z','attributes':{'service.name':'api'}}
            ws.runtime_ingest('opentelemetry',[rec])
            with self.assertRaises(TransactionConflict): ws.runtime_ingest('opentelemetry',[{**rec,'status':'error'}])
        finally: ws.close();td.cleanup()

    def test_dap_structural_secret_redaction_and_runtime_batch_no_silent_truncation(self):
        td,project,ws=self.make_ws()
        try:
            dap={'seq':9,'type':'event','event':'variables','body':{'variables':[{'name':'API_KEY','value':'sk-abcdefghijklmnopqrstuvwxyz'},{'name':'normal','value':'visible'}]}}
            out=ws.runtime_ingest('dap',[dap]); row=ws.store.runtime_event(out['events'][0]['id']); blob=row['attributes_json']
            self.assertNotIn('abcdefghijklmnopqrstuvwxyz',blob); self.assertIn('visible',blob)
            with self.assertRaises(ValueError): ws.runtime_ingest('opentelemetry',[{'name':'x'}]*2001)
        finally: ws.close();td.cleanup()

    def test_runtime_store_is_append_only_and_dap_reconnect_replay_is_idempotent(self):
        td,project,ws=self.make_ws()
        try:
            dap={'session_id':'debug-session-1','seq':42,'type':'event','event':'stopped','body':{'reason':'breakpoint','threadId':1}}
            first=ws.runtime_ingest('dap',[dap]); self.assertEqual(first['ingested'],1)
            second=ws.runtime_ingest('dap',[dap]); self.assertEqual(second['ingested'],0)
            event_id=first['events'][0]['id']; row=ws.store.runtime_event(event_id); self.assertIsNotNone(row)
            attrs=json.loads(row['attributes_json']); self.assertEqual(attrs['habitat.dap.replay_identity'],'session-seq-event')
            conflicting=dict(first['events'][0]); conflicting.pop('line',None); conflicting['status']='different'
            with self.assertRaises(Exception): ws.store.append_runtime_event(conflicting)
        finally: ws.close();td.cleanup()

    def test_dap_without_session_identity_discloses_replay_identity_unavailable(self):
        td,project,ws=self.make_ws()
        try:
            out=ws.runtime_ingest('dap',[{'seq':7,'type':'event','event':'output','body':{'output':'hello'}}])
            row=ws.store.runtime_event(out['events'][0]['id']); attrs=json.loads(row['attributes_json'])
            self.assertEqual(attrs['habitat.dap.replay_identity'],'unavailable')
        finally: ws.close();td.cleanup()

    def test_observatory_agent_health_discloses_stale_and_loop_state(self):
        td,project,ws=self.make_ws(); obs=None
        try:
            a=ws.agent_open('Agent A')
            aid=a['id']
            # Repeated visible tool operations provide a loop-risk signal without reading private reasoning.
            for _ in range(8): ws.activity_emit('tool.started','tool',agent_id=aid,ref_id='workspace.inspect',status='running',summary='inspect again')
            # A pending invalidation is stronger than loop risk for the agent chip/state.
            ws.store.append_agent_notification({'id':'notif:a13','agent_id':aid,'kind':'source-invalidated','resource_kind':'path','resource_id':'app.py','revision':ws.revision,'caused_by_transaction':None,'data':{},'status':'pending','created_at':'2026-01-01T00:00:00Z','acked_at':None})
            obs=ws.observatory_start(port=0,open_browser=False)
            conn=http.client.HTTPConnection('127.0.0.1',obs['port'],timeout=5); conn.request('GET','/api/snapshot'); r=conn.getresponse(); snap=json.loads(r.read()); conn.close()
            health=snap['observer_health']['agents'][aid]
            self.assertEqual(health['status'],'stale'); self.assertEqual(health['pending_invalidations'],1)
            self.assertEqual(snap['agents'][0]['health']['status'],'stale')
        finally:
            if obs: ws.observatory_stop()
            ws.close();td.cleanup()

    def test_failed_test_name_bounding_is_explicit_not_silent(self):
        from habitat.testing.normalize import normalize_test_output
        lines='\n'.join(f'FAILED tests/test_many.py::test_{i}' for i in range(125))+'\n125 failed'
        out=normalize_test_output('python.pytest',lines,'',1,False)
        self.assertEqual(len(out['failed_tests']),100)
        self.assertEqual(out['failed_tests_total'],125)
        self.assertTrue(out['failed_tests_truncated'])


if __name__=='__main__': unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace


class Alpha14ExecutiveTrajectoryTests(unittest.TestCase):
    def make_ws(self):
        td=tempfile.TemporaryDirectory(); base=Path(td.name); project=base/'project'; project.mkdir()
        (project/'app.py').write_text('def f(x):\n    return x + 1\n',encoding='utf-8')
        (project/'tests').mkdir(); (project/'tests'/'test_app.py').write_text('from app import f\n\ndef test_f():\n    assert f(1) == 2\n',encoding='utf-8')
        ws=HabitatWorkspace.create(project,base/'habitat')
        return td,project,ws

    @staticmethod
    def admit_successful_run(ws: HabitatWorkspace, ref='run-ok') -> str:
        ws.store.save_json('runs',ref,{'id':ref,'exit_code':0,'structured':{'status':'passed'},'revision':ws.revision})
        return ref

    @staticmethod
    def advance_to_dispatch(ws: HabitatWorkspace, trajectory_id: str) -> None:
        for phase,operation in (
            ('UPDATE','refresh world state'),
            ('DIAGNOSE','diagnose goal state'),
            ('RETRIEVE','retrieve bounded evidence'),
            ('COMPOSE','compose candidate plan'),
            ('DISPATCH','dispatch bounded action'),
        ):
            ws.executive_advance(trajectory_id,phase,operation,status='passed',progress=True)

    @classmethod
    def advance_to_verified_reflection(cls, ws: HabitatWorkspace, trajectory_id: str, ref: str) -> None:
        cls.advance_to_dispatch(ws,trajectory_id)
        ws.executive_advance(trajectory_id,'VERIFY','verify postcondition',status='passed',progress=True,ref_id=ref)
        ws.executive_advance(trajectory_id,'REFLECT','reflect on verifier result',status='passed',progress=True)

    def test_trajectory_chain_and_milestone_dependency_plan(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Safely improve f')
            m1=ws.executive_milestone_add(tr['id'],'Understand current behavior','Current behavior is explicitly verified',priority='high')
            m2=ws.executive_milestone_add(tr['id'],'Change implementation','New implementation satisfies tests',priority='high',dependencies=[m1['id']])
            plan=ws.executive_plan(tr['id'])
            self.assertEqual(plan['next']['milestone_id'],m1['id'])
            self.assertEqual(plan['hierarchy']['ready_count'],1)
            self.assertTrue(ws.executive_status(tr['id'])['trajectory_chain']['valid'])
            with self.assertRaises(ValueError):
                ws.executive_milestone_update(tr['id'],m2['id'],status='in_progress')
        finally: ws.close();td.cleanup()

    def test_high_milestone_requires_real_successful_verifier_artifact(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Verify a change')
            m=ws.executive_milestone_add(tr['id'],'Verify','Tests pass',priority='critical')
            with self.assertRaises(ValueError):
                ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref='invented-proof')
            ws.store.save_json('runs','bad-run',{'id':'bad-run','exit_code':1,'structured':{'status':'failed'}})
            with self.assertRaises(ValueError):
                ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref='bad-run')
            ref=self.admit_successful_run(ws)
            done=ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref=ref)
            self.assertEqual(done['status'],'passed')
            self.assertEqual(done['verifier_ref'],ref)
        finally: ws.close();td.cleanup()

    def test_completion_gate_blocks_unresolved_contradiction_then_closes(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Complete only with proof')
            m=ws.executive_milestone_add(tr['id'],'Verify behavior','Behavior is verified',priority='high')
            ref=self.admit_successful_run(ws)
            ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref=ref)
            self.advance_to_verified_reflection(ws,tr['id'],ref)
            contradiction=ws.epistemic_create('contradiction','Two sources disagree about f behavior')
            with self.assertRaises(ValueError): ws.executive_complete(tr['id'])
            gate=ws.executive_status(tr['id'])['completion_gate']
            self.assertIn('UNRESOLVED_CONTRADICTION',{x['code'] for x in gate['blockers']})
            ws.epistemic_update(contradiction['id'],status='resolved')
            completed=ws.executive_complete(tr['id'],outcome={'result':'verified'})
            self.assertEqual(completed['status'],'completed')
            self.assertTrue(completed['trajectory_chain']['valid'])
            self.assertEqual(completed['events'][-1]['phase'],'CLOSE')
            self.assertTrue(completed['completion_gate']['ready'])
        finally: ws.close();td.cleanup()

    def test_verification_stales_after_revision_change(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Revision-bound verification')
            m=ws.executive_milestone_add(tr['id'],'Verify','Current revision passes',priority='high')
            ref=self.admit_successful_run(ws)
            ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref=ref)
            self.advance_to_verified_reflection(ws,tr['id'],ref)
            (project/'app.py').write_text('def f(x):\n    return x + 2\n',encoding='utf-8'); ws.refresh()
            gate=ws.executive_status(tr['id'])['completion_gate']
            self.assertFalse(gate['ready'])
            self.assertIn('VERIFICATION_STALE',{x['code'] for x in gate['blockers']})
            with self.assertRaises(ValueError): ws.executive_complete(tr['id'])
        finally: ws.close();td.cleanup()

    def test_failed_step_preserves_negative_memory_and_switches_strategy(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Recover from failed verification')
            self.advance_to_dispatch(ws,tr['id'])
            out=ws.executive_advance(tr['id'],'VERIFY','candidate verification',status='failed',progress=False,data={'reason':'tests failed'})
            self.assertIsNotNone(out['strategy_switch'])
            self.assertEqual(out['trajectory']['current_strategy'],'causal-intervention')
            memories=ws.memory_recall('tests failed',kinds=['failure'])['memories']
            self.assertTrue(any(m['kind']=='failure' and m['provenance'].get('trajectory_id')==tr['id'] for m in memories))
            self.assertTrue(out['trajectory']['trajectory_chain']['valid'])
        finally: ws.close();td.cleanup()

    def test_structured_failure_overrides_zero_exit_code_and_stale_receipts_are_rejected(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Trust verifier semantics and revision')
            m=ws.executive_milestone_add(tr['id'],'Verify exactly','Current revision is proven',priority='critical')
            ws.store.save_json('runs','conflicting-run',{'id':'conflicting-run','exit_code':0,'structured':{'status':'failed'},'revision':ws.revision})
            with self.assertRaises(ValueError):
                ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref='conflicting-run')
            stale=self.admit_successful_run(ws,'stale-run')
            self.advance_to_dispatch(ws,tr['id'])
            (project/'app.py').write_text('def f(x):\n    return x + 2\n',encoding='utf-8'); ws.refresh()
            with self.assertRaises(ValueError):
                ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref=stale)
            with self.assertRaises(ValueError):
                ws.executive_advance(tr['id'],'VERIFY','stale verification',status='passed',ref_id=stale,progress=True)
        finally: ws.close();td.cleanup()

    def test_real_execution_receipt_is_revision_bound_and_cannot_be_reused_after_source_change(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Bind real verifier receipt to source revision')
            m=ws.executive_milestone_add(tr['id'],'Verify real run','Real test receipt proves current revision',priority='critical')
            run=ws.run('python.pytest',20)
            self.assertEqual(run['workspace_revision'],ws.revision)
            stored=ws.store.load_json('runs',run['id'])
            self.assertEqual(stored['workspace_revision'],ws.revision)
            (project/'app.py').write_text('def f(x):\n    return x + 2\n',encoding='utf-8'); ws.refresh()
            with self.assertRaises(ValueError):
                ws.executive_milestone_update(tr['id'],m['id'],status='passed',verifier_ref=run['id'])
        finally: ws.close();td.cleanup()

    def test_manifest_schema10_requires_executive_but_schema9_remains_compatible(self):
        import jsonschema
        td,project,ws=self.make_ws()
        try:
            schema=json.loads((Path(__file__).parents[1]/'schemas'/'workspace-manifest.schema.json').read_text())
            self.assertEqual(ws.manifest['schema'],10)
            self.assertTrue(ws.manifest['world_model']['executive_trajectory'])
            jsonschema.validate(ws.manifest,schema)
            historical=json.loads(json.dumps(ws.manifest)); historical['schema']=9; historical['world_model'].pop('executive_trajectory',None)
            jsonschema.validate(historical,schema)
            broken=json.loads(json.dumps(ws.manifest)); broken['world_model'].pop('executive_trajectory',None)
            with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(broken,schema)
        finally: ws.close();td.cleanup()

    def test_alpha14_machine_contracts_validate_emitted_objects(self):
        import jsonschema
        from habitat.observatory import ObservatoryReadModel
        td,project,ws=self.make_ws()
        try:
            base=Path(__file__).parents[1]/'schemas'
            load=lambda name: json.loads((base/name).read_text())
            tr=ws.executive_start('Validate emitted executive contracts')
            m=ws.executive_milestone_add(tr['id'],'Inspect contracts','Schemas admit emitted objects',priority='medium')
            jsonschema.validate(ws.executive_status(tr['id']),load('executive-trajectory.schema.json'))
            jsonschema.validate(m,load('executive-milestone.schema.json'))
            jsonschema.validate(ws.executive_plan(tr['id']),load('executive-plan.schema.json'))
            jsonschema.validate(ws.world_health(),load('world-health.schema.json'))
            jsonschema.validate(ws.world_summary(),load('world-summary.schema.json'))
            snapshot=ObservatoryReadModel(ws).snapshot()
            jsonschema.validate(snapshot,load('observatory-snapshot.schema.json'))
            self.assertEqual(len(snapshot['executive']['trajectories']),1)
            self.assertEqual(len(snapshot['executive']['milestones']),1)
        finally: ws.close();td.cleanup()

    def test_phase_skipping_is_rejected_and_plan_exposes_allowed_control_phase(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Enforce control sequence')
            plan=ws.executive_plan(tr['id'])
            self.assertIn('UPDATE',plan['control']['allowed_next_phases'])
            with self.assertRaises(ValueError):
                ws.executive_advance(tr['id'],'DIAGNOSE','skip update',status='passed',progress=True)
            ws.executive_advance(tr['id'],'UPDATE','update world',status='passed',progress=True)
            self.assertTrue(ws.executive_status(tr['id'])['phase_sequence']['valid'])
        finally: ws.close();td.cleanup()

    def test_hard_step_budget_stops_unbounded_execution_and_allows_explicit_stop(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Bound work',budget={'max_steps':1,'max_strategy_switches':1})
            ws.executive_advance(tr['id'],'UPDATE','one admitted step',status='passed',progress=True)
            plan=ws.executive_plan(tr['id'])
            self.assertTrue(plan['budget']['exhausted'])
            self.assertIn('STEP_BUDGET_EXHAUSTED',plan['budget']['reasons'])
            self.assertEqual(plan['next']['operation'],'stop-budget-exhausted')
            self.assertIn('executive-budget-exhausted',{x['kind'] for x in ws.world_health()['blockers']})
            with self.assertRaises(RuntimeError):
                ws.executive_advance(tr['id'],'DIAGNOSE','over budget',status='passed',progress=True)
            stopped=ws.executive_stop(tr['id'],status='abandoned',reason='step budget exhausted')
            self.assertEqual(stopped['status'],'abandoned')
            self.assertTrue(stopped['trajectory_chain']['valid'])
            self.assertTrue(stopped['phase_sequence']['valid'])
        finally: ws.close();td.cleanup()

    def test_repeated_failure_cannot_cosmetically_reuse_same_strategy_family(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Force structural recovery',initial_strategy='causal-intervention')
            self.advance_to_dispatch(ws,tr['id'])
            out=ws.executive_advance(tr['id'],'VERIFY','candidate rejected',status='failed',data={'reason':'tests failed'})
            self.assertIsNotNone(out['strategy_switch'])
            self.assertNotEqual(out['trajectory']['current_strategy'],'causal-intervention')
            self.assertEqual(out['strategy_switch']['data']['to'],'scope-reduction')
        finally: ws.close();td.cleanup()

    def test_protocol_exposes_executive_surface(self):
        td,project,ws=self.make_ws()
        try:
            proto=HabitatProtocol(ws)
            rsp=proto.handle({'id':'1','method':'workspace.executive.start','params':{'goal':'Protocol-governed task'}})
            self.assertTrue(rsp['ok']); tid=rsp['result']['id']
            p=proto.handle({'id':'2','method':'workspace.executive.plan','params':{'trajectory_id':tid}})
            self.assertTrue(p['ok']); self.assertEqual(p['result']['trajectory_id'],tid)
            caps=proto.handle({'id':'3','method':'protocol.capabilities','params':{}})
            self.assertIn('workspace.executive.complete',caps['result']['methods'])
            self.assertIn('workspace.executive.stop',caps['result']['methods'])
        finally: ws.close();td.cleanup()

    def test_assurance_chain_is_not_silently_truncated_after_one_thousand_events(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Long horizon chain integrity')
            from habitat.util import utc_now
            for i in range(1005):
                ws.store.append_executive_event({'trajectory_id':tr['id'],'phase':'COMPOSE','operation':'auxiliary-note','status':'passed',
                    'revision':ws.revision,'ref_id':None,'data':{'i':i},'created_at':utc_now()})
            ws.store.conn.execute("UPDATE executive_events SET operation='tail-tampered' WHERE trajectory_id=? AND ordinal=1003",(tr['id'],)); ws.store.conn.commit()
            status=ws.executive_status(tr['id'])
            self.assertGreater(status['event_count'],1000)
            self.assertFalse(status['trajectory_chain']['valid'])
            self.assertEqual(status['trajectory_chain']['failure']['seq'],1003)
        finally: ws.close();td.cleanup()

    def test_chain_tampering_is_detected(self):
        td,project,ws=self.make_ws()
        try:
            tr=ws.executive_start('Tamper-evident trajectory')
            ws.executive_advance(tr['id'],'UPDATE','inspect state',status='passed',progress=True)
            ws.store.conn.execute("UPDATE executive_events SET operation='tampered' WHERE trajectory_id=? AND ordinal=2",(tr['id'],)); ws.store.conn.commit()
            status=ws.executive_status(tr['id'])
            self.assertFalse(status['trajectory_chain']['valid'])
            self.assertIn('TRAJECTORY_CHAIN_INVALID',{x['code'] for x in status['completion_gate']['blockers']})
        finally: ws.close();td.cleanup()


if __name__=='__main__': unittest.main()

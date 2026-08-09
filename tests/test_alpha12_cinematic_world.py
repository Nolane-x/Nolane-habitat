from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import habitat
from habitat.workspace import HabitatWorkspace
from habitat.mutation import TransactionConflict


class Alpha12CinematicWorldTests(unittest.TestCase):
    def make_ws(self):
        td=tempfile.TemporaryDirectory(); base=Path(td.name); project=base/'project';project.mkdir()
        (project/'src').mkdir();(project/'tests').mkdir();(project/'.github').mkdir();(project/'.github'/'workflows').mkdir(parents=True,exist_ok=True)
        (project/'src'/'auth.py').write_text(
            'import os\n\n'
            'def normalize_email(email):\n    return email.strip().lower()\n\n'
            'def authorize(user, cursor):\n'
            '    email = normalize_email(user.email)\n'
            '    cursor.execute("SELECT role FROM users WHERE email=?", (email,))\n'
            '    if not user.active:\n        raise PermissionError("inactive")\n'
            '    return {"role": "admin" if user.is_admin else "user", "env": os.getenv("APP_ENV")}\n',encoding='utf-8')
        (project/'tests'/'test_auth.py').write_text('def test_placeholder():\n    assert True\n',encoding='utf-8')
        (project/'package.json').write_text(json.dumps({'name':'demo-ui','scripts':{'test':'pytest','build':'vite'}}),encoding='utf-8')
        (project/'docker-compose.yml').write_text('services:\n  api:\n    depends_on:\n      - db\n  db:\n    image: postgres:16\n',encoding='utf-8')
        (project/'.github'/'workflows'/'ci.yml').write_text('jobs:\n  test:\n    runs-on: ubuntu-latest\n  build:\n    runs-on: ubuntu-latest\n',encoding='utf-8')
        ws=HabitatWorkspace.create(project,base/'habitat')
        return td,project,ws

    def test_effect_twin_records_static_effects_with_trust_boundary(self):
        td,project,ws=self.make_ws()
        try:
            snap=ws.effect_snapshot(path='src/auth.py')
            kinds={x['kind'] for x in snap['effects']}
            self.assertIn('db-query',kinds);self.assertIn('throws',kinds);self.assertIn('returns',kinds);self.assertIn('env-read',kinds)
            self.assertIn('Static Effect Twin',snap['claim_boundary'])
            self.assertTrue(all(x['revision']==ws.revision for x in snap['effects']))
        finally: ws.close();td.cleanup()

    def test_runtime_topology_links_parent_spans_service_route_and_database(self):
        td,project,ws=self.make_ws()
        try:
            a=ws.agent_open('Codex',{})['id']
            ws.runtime_ingest('opentelemetry',[
                {'trace_id':'t1','span_id':'s1','name':'POST /login','duration_ms':4.2,'attributes':{'service.name':'api','http.route':'/login'}},
                {'trace_id':'t1','span_id':'s2','parent_span_id':'s1','name':'SELECT users','duration_ms':1.1,'attributes':{'service.name':'api','db.system':'postgresql','db.name':'users'}},
            ],agent_id=a)
            topo=ws.runtime_topology(agent_id=a)
            labels={n['label'] for n in topo['nodes']}; kinds={e['kind'] for e in topo['edges']}
            self.assertIn('api',labels);self.assertIn('/login',labels);self.assertIn('postgresql/users',labels);self.assertIn('span-child',kinds)
            self.assertIn('Observed telemetry topology',topo['claim_boundary'])
        finally: ws.close();td.cleanup()

    def test_project_world_parses_compose_ci_and_package_tasks(self):
        td,project,ws=self.make_ws()
        try:
            world=ws.project_world(); labels={n['label'] for n in world['nodes']}; kinds={e['kind'] for e in world['edges']}
            self.assertTrue({'api','db','test','build'} <= labels)
            self.assertIn('depends-on',kinds);self.assertIn('exposes-task',kinds)
            self.assertIn('not complete deployment/runtime truth',world['claim_boundary'])
        finally: ws.close();td.cleanup()

    def test_counterfactual_world_isolated_until_promoted(self):
        td,project,ws=self.make_ws()
        try:
            agent=ws.agent_open('Codex',{})['id']; before=(project/'src'/'auth.py').read_text()
            w=ws.counterfactual_fork('remove admin elevation',agent_id=agent)
            applied=ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'src/auth.py','old':'"admin" if user.is_admin else "user"','new':'"user"'}])
            self.assertFalse(applied['canonical_changed']);self.assertEqual((project/'src'/'auth.py').read_text(),before)
            ev=ws.counterfactual_evaluate(w['id']);self.assertFalse(ev['canonical_changed']);self.assertTrue(ev['paths'][0]['parse_complete'])
            promoted=ws.counterfactual_promote(w['id'],agent_id=agent)
            self.assertEqual(promoted['world']['status'],'promoted');self.assertIn('"role": "user"',(project/'src'/'auth.py').read_text())
        finally: ws.close();td.cleanup()

    def test_counterfactual_world_refuses_new_patch_after_base_revision_drift(self):
        td,project,ws=self.make_ws()
        try:
            w=ws.counterfactual_fork('alternative')
            (project/'tests'/'test_auth.py').write_text('def test_placeholder():\n    assert 1 == 1\n# drift\n',encoding='utf-8');ws.refresh_paths(['tests/test_auth.py'])
            with self.assertRaises(TransactionConflict):
                ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'src/auth.py','old':'return email.strip().lower()','new':'return email.lower()'}])
        finally: ws.close();td.cleanup()

    def test_cognition_plan_prioritizes_stale_world_and_contradiction(self):
        td,project,ws=self.make_ws()
        try:
            a=ws.agent_open('Codex',{})['id']
            ctx=ws.orient('fix auth',agent_id=a);ep=ws.episode_start('fix auth',ctx.handle)
            ws.epistemic_create('contradiction','static policy says admin but observed runtime returns user',agent_id=a,episode_id=ep['id'])
            plan=ws.cognition_plan(a,ep['id'])
            self.assertEqual(plan['next']['operation'],'discriminate-contradiction');self.assertEqual(plan['next']['expected_information_gain'],'high')
            self.assertIn('not hidden chain-of-thought',plan['claim_boundary'])
        finally: ws.close();td.cleanup()

    def test_dataflow_twin_tracks_assignment_call_and_runtime_correlation(self):
        td,project,ws=self.make_ws()
        try:
            path=project/'src'/'flow.py'
            path.write_text('def normalize(x):\n    return x.strip()\n\ndef run(request):\n    email = normalize(request.email)\n    return email\n',encoding='utf-8')
            ws.refresh_paths(['src/flow.py'])
            snap=ws.dataflow_snapshot(path='src/flow.py')
            kinds={x['kind'] for x in snap['flows']}
            self.assertTrue({'argument-to-call','call-result','return-flow'}.issubset(kinds))
            aid=ws.agent_open('runtime-flow')['id']
            ws.runtime_ingest('opentelemetry',[{'trace_id':'t','span_id':'s','name':'run','attributes':{'code.file.path':str(path),'code.line.number':4}}],agent_id=aid)
            correlated=ws.dataflow_snapshot(path='src/flow.py')
            self.assertTrue(any(x['observed_runtime_refs'] for x in correlated['flows']))
            self.assertIn('not dynamic value-flow',correlated['claim_boundary'])
        finally:
            ws.close(); td.cleanup()

    def test_counterfactual_verify_runs_in_disposable_copy_and_preserves_canonical(self):
        td,project,ws=self.make_ws()
        try:
            before=(project/'src/auth.py').read_text(encoding='utf-8')
            w=ws.counterfactual_fork('verification copy')
            ws.counterfactual_apply(w['id'],[{'op':'replace_text','path':'src/auth.py','old':'email = normalize_email(user.email)','new':'email = normalize_email(str(user.email))'}])
            result=ws.counterfactual_verify(w['id'],timeout_s=30)
            self.assertIn(result['status'],{'passed','failed'})
            self.assertFalse(result['canonical_changed']); self.assertEqual((project/'src/auth.py').read_text(encoding='utf-8'),before)
            self.assertIn('disposable source copy',result['claim_boundary'])
        finally:
            ws.close();td.cleanup()

    def test_multi_observation_same_path_emits_one_invalidation_per_agent(self):
        td,project,ws=self.make_ws()
        try:
            owner=ws.agent_open('owner',{})['id']; observer=ws.agent_open('observer',{})['id']
            ws.agent_observe(observer,'src/auth.py',object_id='symbol:a'); ws.agent_observe(observer,'src/auth.py',object_id='symbol:b')
            tx=ws.stage_change([{'op':'replace_text','path':'src/auth.py','old':'email = normalize_email(user.email)','new':'email = normalize_email(str(user.email))'}],agent_id=owner)
            committed=ws.commit_change(tx['id'],owner)
            notes=ws.agent_notifications(observer,'pending',100)['notifications']
            self.assertEqual(len([n for n in notes if n['resource_id']=='src/auth.py']),1)
            self.assertEqual(len(committed.get('coordination_notifications') or []),1)
        finally:
            ws.close();td.cleanup()

    def test_dataflow_augassign_persists_metadata_without_corrupting_trust(self):
        td,project,ws=self.make_ws()
        try:
            path=project/'src'/'counter.py'
            path.write_text('def bump(total, delta):\n    total += delta\n    return total\n',encoding='utf-8')
            ws.refresh_paths(['src/counter.py'])
            snap=ws.dataflow_snapshot(path='src/counter.py')
            assigns=[x for x in snap['flows'] if x['kind']=='assigns']
            self.assertTrue(assigns)
            self.assertTrue(all(x['trust']=='parser' for x in assigns))
            self.assertTrue(any(x.get('metadata',{}).get('operator')=='Add' for x in assigns))
        finally:
            ws.close();td.cleanup()

    def test_release_identity_contract_remains_consistent_after_alpha12(self):
        base=Path(__file__).resolve().parents[1]
        version=(base/'VERSION').read_text().strip()
        self.assertEqual(version,habitat.__version__)
        pep=version.replace('-alpha.','a')
        text=(base/'pyproject.toml').read_text();self.assertIn(f'version = "{pep}"',text)


if __name__=='__main__': unittest.main()

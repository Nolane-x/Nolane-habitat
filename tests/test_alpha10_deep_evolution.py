from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace


class Alpha10DeepEvolutionTests(unittest.TestCase):
    def make_ws(self, files: dict[str,str] | None = None):
        td=tempfile.TemporaryDirectory(); base=Path(td.name); root=base/'project'; hab=base/'habitat'; root.mkdir()
        for rel,text in (files or {'auth.py':'def value():\n    return 1\n'}).items():
            p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')
        ws=HabitatWorkspace.create(root,hab)
        self.addCleanup(td.cleanup)
        self.addCleanup(ws.close)
        return ws,root,hab

    def test_observed_read_set_generates_selective_revalidation_notification(self):
        ws,root,_=self.make_ws()
        a=ws.agent_open('agent-a')['id']; b=ws.agent_open('agent-b')['id']
        ws.agent_observe(a,'auth.py')
        tx=ws.stage_change([{'op':'replace_text','path':'auth.py','old':'return 1','new':'return 2'}],agent_id=b)
        result=ws.commit_change(tx['id'],b)
        self.assertTrue(result.get('coordination_notifications'))
        notes=ws.agent_notifications(a)
        self.assertEqual(notes['count'],1); self.assertEqual(notes['notifications'][0]['kind'],'source-invalidated')
        self.assertEqual(notes['notifications'][0]['data']['action'],'selective-revalidate')
        ack=ws.agent_ack_notification(a,notes['notifications'][0]['id']); self.assertTrue(ack['acked'])

    def test_agent_private_residency_does_not_cross_agent_namespace(self):
        ws,_,_=self.make_ws()
        a=ws.agent_open('agent-a')['id']; b=ws.agent_open('agent-b')['id']
        ctx=ws.orient('value function',agent_id=a)
        admitted=ws.agent_residency_admit(a,ctx.handle,max_admit=4)
        self.assertGreaterEqual(len(admitted['admitted']),1)
        self.assertGreater(ws.agent_residency_status(a)['count'],0)
        self.assertEqual(ws.agent_residency_status(b)['count'],0)

    def test_change_policy_plan_supports_path_scoped_approval_without_side_effects(self):
        ws,root,_=self.make_ws({'src/a.py':'x=1\n','billing/pay.py':'amount=1\n'})
        ws.policy_update({'source':{'approval':['billing/**']}})
        plan=ws.change_plan([{'op':'replace_text','path':'billing/pay.py','old':'1','new':'2'}])
        self.assertTrue(plan['approval_required']); self.assertFalse(plan['allowed_without_approval']); self.assertFalse(plan['side_effects']); self.assertEqual(plan['risk'],'high')
        self.assertEqual((root/'billing/pay.py').read_text(),'amount=1\n')
        with self.assertRaises(PermissionError): ws.stage_change([{'op':'replace_text','path':'billing/pay.py','old':'1','new':'2'}])
        approval=ws.approval_grant('edit',resource=None,granted_by='reviewer')
        tx=ws.stage_change([{'op':'replace_text','path':'billing/pay.py','old':'1','new':'2'}],approval_id=approval['id']); ws.commit_change(tx['id'])
        self.assertEqual((root/'billing/pay.py').read_text(),'amount=2\n')

    def test_structural_approval_token_is_single_use_and_host_scoped(self):
        ws,root,_=self.make_ws()
        ws.policy_update({'structural_mutation':{'approval_required':True}})
        with self.assertRaises(PermissionError):
            ws.stage_change([{'op':'create_file','path':'new.py','content':'x=1\n'}])
        approval=ws.approval_grant('edit',resource=None,granted_by='human-reviewer')
        tx=ws.stage_change([{'op':'create_file','path':'new.py','content':'x=1\n'}],approval_id=approval['id'])
        ws.commit_change(tx['id']); self.assertTrue((root/'new.py').is_file())
        with self.assertRaises(PermissionError):
            ws.stage_change([{'op':'create_file','path':'again.py','content':'x=2\n'}],approval_id=approval['id'])

    def test_retention_compacts_only_selected_non_authoritative_history(self):
        ws,_,_=self.make_ws()
        a=ws.agent_open('agent-a')['id']; b=ws.agent_open('agent-b')['id']; ws.agent_observe(a,'auth.py')
        tx=ws.stage_change([{'op':'replace_text','path':'auth.py','old':'return 1','new':'return 2'}],agent_id=b); ws.commit_change(tx['id'],b)
        note=ws.agent_notifications(a)['notifications'][0]; ws.agent_ack_notification(a,note['id'])
        plan=ws.retention_compact({'max_acked_notifications':0},dry_run=True)
        self.assertGreaterEqual(plan['deletable']['acked_notifications'],1)
        actual=ws.retention_compact({'max_acked_notifications':0},dry_run=False)
        self.assertGreaterEqual(actual['deleted']['acked_notifications'],1)
        self.assertIsNotNone(ws.store.head_revision())

    def test_state_files_are_posix_private_when_supported(self):
        ws,_,hab=self.make_ws()
        if os.name!='nt':
            self.assertEqual(stat.S_IMODE(hab.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE((hab/'habitat.sqlite3').stat().st_mode),0o600)

    def test_lock_aware_dependency_world_resolves_direct_version(self):
        ws,_,_=self.make_ws({
            'package.json':json.dumps({'dependencies':{'lodash':'^4.17.0'}}),
            'package-lock.json':json.dumps({'lockfileVersion':3,'packages':{'node_modules/lodash':{'version':'4.17.21'}}}),
        })
        world=ws.dependencies_world(); match=[x for x in world['resolved_direct'] if x['name']=='lodash']
        self.assertEqual(match[0]['locked_version'],'4.17.21'); self.assertFalse(world['unlocked_direct'])

    def test_repository_guidance_is_discovered_but_not_auto_injected(self):
        ws,_,_=self.make_ws({'src/a.py':'x=1\n','AGENTS.md':'Only edit src/.\n','src/CLAUDE.md':'Run targeted tests.\n','.github/copilot-instructions.md':'Keep diffs small.\n'})
        d=ws.guidance_discover(); self.assertEqual(d['count'],3); self.assertFalse(d['automatic_context_injection'])
        self.assertTrue(all(not x['auto_injected'] for x in d['guidance']))
        read=ws.guidance_read('AGENTS.md',max_lines=10); self.assertIn('Only edit src',read['source']); self.assertTrue(read['guidance_only'])
        with self.assertRaises(ValueError): ws.guidance_read('src/a.py')

    def test_world_summary_and_state_security_are_bounded_orientation_surfaces(self):
        ws,_,_=self.make_ws({'a.py':'x=1\n','requirements.txt':'requests>=2\n'})
        summary=ws.world_summary()
        self.assertEqual(summary['revision'],ws.revision)
        self.assertIn('dependencies',summary); self.assertEqual(summary['dependencies']['direct'],1)
        self.assertIn('execution_security',summary); self.assertIn('claim_boundary',summary)
        sec=ws.state_security(); self.assertFalse(sec['encryption_at_rest']); self.assertIn('not encrypted',sec['claim_boundary'])

    def test_git_branch_worktree_conflict_and_commit_impact_surfaces(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); base=Path(td.name); root=base/'repo'; root.mkdir()
        subprocess.run(['git','-C',str(root),'init','-q'],check=True); subprocess.run(['git','-C',str(root),'config','user.email','a@example.test'],check=True); subprocess.run(['git','-C',str(root),'config','user.name','A'],check=True)
        (root/'a.py').write_text('x=1\n'); subprocess.run(['git','-C',str(root),'add','.'],check=True); subprocess.run(['git','-C',str(root),'commit','-qm','initial'],check=True)
        ws=HabitatWorkspace.create(root,base/'hab'); self.addCleanup(ws.close)
        self.assertGreaterEqual(ws.git_branches()['count'],1)
        self.assertGreaterEqual(ws.git_worktrees()['count'],1)
        self.assertFalse(ws.git_conflicts()['conflicted'])
        impact=ws.git_commit_impact('HEAD'); self.assertEqual(impact['file_count'],1); self.assertEqual(impact['files'][0]['path'],'a.py')

    def test_git_temporal_cognition_churn_diff_and_symbol_explanation(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); base=Path(td.name); root=base/'repo'; root.mkdir()
        subprocess.run(['git','-C',str(root),'init','-q'],check=True); subprocess.run(['git','-C',str(root),'config','user.email','a@example.test'],check=True); subprocess.run(['git','-C',str(root),'config','user.name','A'],check=True)
        (root/'auth.py').write_text('def value():\n    return 1\n',encoding='utf-8'); subprocess.run(['git','-C',str(root),'add','.'],check=True); subprocess.run(['git','-C',str(root),'commit','-qm','initial value'],check=True)
        (root/'auth.py').write_text('def value():\n    return 2\n',encoding='utf-8'); subprocess.run(['git','-C',str(root),'commit','-qam','change value'],check=True)
        ws=HabitatWorkspace.create(root,base/'hab'); self.addCleanup(ws.close)
        churn=ws.git_churn('auth.py'); self.assertGreaterEqual(churn['commits'],2)
        changed=ws.git_changed_files('HEAD'); self.assertTrue(any(x.get('path')=='auth.py' for x in changed['files']))
        diff=ws.git_diff('HEAD~1'); self.assertIn('return 2',diff['diff'])
        sym=ws.store.conn.execute("SELECT id FROM symbols WHERE name='value'").fetchone()['id']
        expl=ws.git_explain_symbol(sym); self.assertTrue(expl['available']); self.assertGreaterEqual(len(expl['commits']),1)

    def test_full_sandbox_profile_never_silently_downgrades(self):
        ws,_,_=self.make_ws()
        status=ws.sandbox_status(); b=status['host']['bubblewrap']
        if b.get('available'):
            configured=ws.execution_configure('filesystem-contained'); self.assertTrue(configured['full_sandbox'])
            self.assertTrue(configured['filesystem_restricted'])
        else:
            with self.assertRaises(RuntimeError): ws.execution_configure('filesystem-contained')
            self.assertFalse(ws.execution_security()['full_sandbox'])

    def test_protocol_exposes_coordination_retention_temporal_and_dependency_world(self):
        ws,_,_=self.make_ws(); proto=HabitatProtocol(ws); methods=set(proto.METHODS)
        for name in ('workspace.agent.notifications','workspace.agent.residency.admit','workspace.retention.compact','workspace.sandbox.status','workspace.git.churn','workspace.dependencies.world','workspace.hypothesis.compare'):
            self.assertIn(name,methods)

    def test_agent_forget_deletes_private_cognition_but_preserves_shared_world(self):
        ws,_,_=self.make_ws(); a=ws.agent_open('A')['id']; h=ws.hypothesis_create('shared hypothesis')
        ws.agent_belief_update(a,h['id'],stance='support',confidence=0.8); ws.agent_observe(a,'auth.py')
        rev=ws.revision; ws.agent_close(a); out=ws.agent_forget(a)
        self.assertTrue(out['forgotten']); self.assertIsNone(ws.store.agent_session(a)); self.assertIsNotNone(ws.store.revision(rev)); self.assertIsNotNone(ws.store.hypothesis(h['id']))
        self.assertIn('revisions',out['preserved_shared_world'])

    def test_shared_hypothesis_allows_agent_specific_belief_views(self):
        ws,_,_=self.make_ws(); a=ws.agent_open('A')['id']; b=ws.agent_open('B')['id']
        h=ws.hypothesis_create('cache invalidation causes stale authorization',prior_confidence=0.5)
        ba=ws.agent_belief_update(a,h['id'],stance='support',confidence=0.8,rationale='trace points to stale cache')
        bb=ws.agent_belief_update(b,h['id'],stance='oppose',confidence=0.7,rationale='reproduction bypasses cache')
        self.assertEqual(ba['stance'],'support'); self.assertEqual(bb['stance'],'oppose')
        self.assertEqual(ws.agent_belief_portfolio(a)['count'],1); self.assertEqual(ws.agent_belief_portfolio(b)['count'],1)
        self.assertEqual(ws.hypothesis_status(h['id'])['current_confidence'],0.5)
        self.assertIn('not verified world state',ba['claim_boundary'])

    def test_hypothesis_portfolio_marks_close_alternatives_for_discrimination(self):
        ws,_,_=self.make_ws()
        h1=ws.hypothesis_create('cache invalidation bug',prior_confidence=0.52)
        h2=ws.hypothesis_create('permission derivation bug',prior_confidence=0.48)
        cmp=ws.hypothesis_compare([h1['id'],h2['id']]); self.assertTrue(cmp['needs_discriminating_experiment'])
        nxt=ws.hypothesis_next_experiment([h1['id'],h2['id']]); self.assertEqual(nxt['priority'],'high')

    def test_pending_read_set_invalidation_blocks_commit_until_selective_revalidation(self):
        ws,root,_=self.make_ws({'a.py':'value = 1\n','b.py':'other = 1\n'})
        a=ws.agent_open('agent-a')['id']; b=ws.agent_open('agent-b')['id']
        ws.agent_observe(a,'b.py')
        txa=ws.stage_change([{'op':'replace_text','path':'a.py','old':'1','new':'2'}],agent_id=a)
        txb=ws.stage_change([{'op':'replace_text','path':'b.py','old':'1','new':'3'}],agent_id=b)
        ws.commit_change(txb['id'],b)
        with self.assertRaises(Exception): ws.commit_change(txa['id'],a)
        note=ws.agent_notifications(a)['notifications'][0]
        revalidated=ws.agent_revalidate_notification(a,note['id']); self.assertTrue(revalidated['acked'])
        out=ws.commit_change(txa['id'],a); self.assertEqual(out['status'],'committed')
        self.assertEqual((root/'a.py').read_text(),'value = 2\n')

    def test_disjoint_revision_change_allows_path_scoped_optimistic_rebase(self):
        ws,root,_=self.make_ws({'a.py':'value = 1\n','b.py':'other = 1\n'})
        tx=ws.stage_change([{'op':'replace_text','path':'a.py','old':'1','new':'2'}])
        (root/'b.py').write_text('other = 2\n',encoding='utf-8')
        ws.reconcile()
        out=ws.commit_change(tx['id'])
        self.assertEqual(out['status'],'committed')
        self.assertEqual((root/'a.py').read_text(encoding='utf-8'),'value = 2\n')
        self.assertIsNotNone(out['rebased_from_revision'])
        self.assertIsNotNone(out['rebased_onto_revision'])

    def test_optimistic_rebase_still_rejects_touched_path_drift(self):
        ws,root,_=self.make_ws({'a.py':'value = 1\n','b.py':'other = 1\n'})
        tx=ws.stage_change([{'op':'replace_text','path':'a.py','old':'1','new':'2'}])
        (root/'a.py').write_text('value = 9\n',encoding='utf-8')
        with self.assertRaises(Exception):
            ws.commit_change(tx['id'])
        self.assertEqual((root/'a.py').read_text(encoding='utf-8'),'value = 9\n')


    def test_project_invariant_registry_links_verifier_and_contradiction_without_claiming_truth(self):
        ws,_,_=self.make_ws({'rules.py':'def enforce():\n    return True\n','tests/test_rules.py':'def test_rule():\n    assert True\n'})
        inv=ws.invariant_create('Every privileged action must be audited',severity='critical')
        sym=ws.store.conn.execute("SELECT id FROM symbols WHERE name='enforce'").fetchone()['id']
        linked=ws.invariant_link(inv['id'],'symbol',sym,relation='implements')
        self.assertEqual(linked['assessment'],'linked-unverified')
        verified=ws.invariant_link(inv['id'],'test','tests/test_rules.py',relation='verifier')
        self.assertEqual(verified['verifier_count'],1)
        contested=ws.invariant_link(inv['id'],'requirement','REQ-legacy-exception',relation='contradicts')
        self.assertEqual(contested['assessment'],'contested')
        self.assertEqual(contested['contradiction_count'],1)
        final=ws.invariant_update(inv['id'],'contested')
        self.assertEqual(final['status'],'contested')
        self.assertIn('does not infer invariant truth',final['claim_boundary'])

    def test_protocol_exposes_invariant_registry(self):
        ws,_,_=self.make_ws(); proto=HabitatProtocol(ws)
        inv=proto.handle({'id':'i','method':'workspace.invariant.create','params':{'statement':'State mutations increment version','severity':'error'}})
        self.assertTrue(inv['ok'])
        got=proto.handle({'id':'s','method':'workspace.invariant.status','params':{'invariant_id':inv['result']['id']}})
        self.assertTrue(got['ok']); self.assertEqual(got['result']['statement'],'State mutations increment version')


    def test_ab_harness_requires_observed_identity_and_independent_evaluator_for_strong_evidence(self):
        base=Path(__file__).parents[1]
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); td=Path(td.name); repo=td/'repo'; repo.mkdir(); (repo/'a.py').write_text('x=1\n')
        suite=td/'suite.json'; suite.write_text(json.dumps({'tasks':[{'id':'t1','repo':str(repo),'prompt':'inspect x'}]}))
        agent=td/'agent.py'; agent.write_text('import json,sys; p=json.load(sys.stdin); print(json.dumps({"task_id":p["task_id"],"success":True,"tool_calls":1,"input_tokens":10,"output_tokens":5,"wall_ms":3,"model_id":"m1","scaffold_id":"s1"}))\n')
        evaluator=td/'eval.py'; evaluator.write_text('import json,sys; json.load(sys.stdin); print(json.dumps({"success":True,"score":1.0}))\n')
        out=td/'out.json'; cmd=f'{os.sys.executable} {agent}'
        subprocess.run([os.sys.executable,str(base/'benchmarks'/'agent_ab_harness.py'),'--suite',str(suite),'--baseline-cmd',cmd,'--habitat-cmd',cmd,'--evaluator-cmd',f'{os.sys.executable} {evaluator}','--repetitions','1','--out',str(out)],check=True,capture_output=True,text=True)
        report=json.loads(out.read_text()); self.assertTrue(report['comparability']['strong_evidence_ready']); self.assertEqual(report['schema'],3)
        out2=td/'out2.json'
        subprocess.run([os.sys.executable,str(base/'benchmarks'/'agent_ab_harness.py'),'--suite',str(suite),'--baseline-cmd',cmd,'--habitat-cmd',cmd,'--repetitions','1','--out',str(out2)],check=True,capture_output=True,text=True)
        self.assertFalse(json.loads(out2.read_text())['comparability']['strong_evidence_ready'])


    def test_release_identity_is_consistent_across_runtime_version_and_package_metadata(self):
        import habitat, re
        from habitat.toml_compat import tomllib
        base=Path(__file__).parents[1]
        version=(base/'VERSION').read_text().strip()
        self.assertEqual(habitat.__version__,version)
        meta=tomllib.loads((base/'pyproject.toml').read_text())
        m=re.fullmatch(r"(\d+\.\d+\.\d+)-alpha\.(\d+)",version); self.assertIsNotNone(m)
        self.assertEqual(meta['project']['version'],f"{m.group(1)}a{m.group(2)}")



if __name__=='__main__': unittest.main()

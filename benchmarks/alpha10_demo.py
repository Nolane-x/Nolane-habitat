#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, tempfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat import shutdown_runtime_services

RELEASE='0.1.0-alpha.10'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out'); args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='habitat-a10-demo-') as td:
        td=Path(td); root=td/'repo'; root.mkdir()
        subprocess.run(['git','init','-q',str(root)],check=True)
        subprocess.run(['git','-C',str(root),'config','user.email','demo@example.test'],check=True)
        subprocess.run(['git','-C',str(root),'config','user.name','Habitat Demo'],check=True)
        (root/'auth.py').write_text('def validate_credentials(user):\n    return bool(user)\n',encoding='utf-8')
        (root/'config.py').write_text('AUTH_MODE = "strict"\n',encoding='utf-8')
        (root/'billing').mkdir(); (root/'billing'/'rules.py').write_text('LIMIT = 100\n',encoding='utf-8')
        (root/'tests').mkdir(); (root/'tests'/'test_auth.py').write_text('import unittest\nfrom auth import validate_credentials\nclass T(unittest.TestCase):\n def test_auth(self): self.assertTrue(validate_credentials("u"))\n',encoding='utf-8')
        (root/'AGENTS.md').write_text('Prefer targeted tests and minimal diffs.\n',encoding='utf-8')
        (root/'package.json').write_text(json.dumps({'dependencies':{'lodash':'^4.17.0'}}),encoding='utf-8')
        (root/'package-lock.json').write_text(json.dumps({'lockfileVersion':3,'packages':{'node_modules/lodash':{'version':'4.17.21'}}}),encoding='utf-8')
        subprocess.run(['git','-C',str(root),'add','.'],check=True); subprocess.run(['git','-C',str(root),'commit','-q','-m','initial cognitive demo'],check=True)
        ws=HabitatWorkspace.create(root,td/'habitat')
        try:
            world_before=ws.world_summary(); guidance=ws.guidance_discover(); state_security=ws.state_security(); sandbox=ws.sandbox_status()
            a=ws.agent_open('agent-A')['id']; b=ws.agent_open('agent-B')['id']
            ctx=ws.orient('fix credential validation while respecting auth mode',12,agent_id=a)
            ws.agent_observe(a,'config.py')
            h=ws.hypothesis_create('falsey-but-present users are rejected by credential validation',prior_confidence=.5)
            belief_a=ws.agent_belief_update(a,h['id'],stance='support',confidence=.72,rationale='validation uses bool(user)')
            belief_b=ws.agent_belief_update(b,h['id'],stance='uncertain',confidence=.45,rationale='auth mode may also matter')
            txa=ws.stage_change([{'op':'replace_text','path':'auth.py','old':'return bool(user)','new':'return user is not None'}],agent_id=a)
            txb=ws.stage_change([{'op':'replace_text','path':'config.py','old':'strict','new':'audited'}],agent_id=b); ws.commit_change(txb['id'],b)
            blocked=None
            try: ws.commit_change(txa['id'],a)
            except Exception as exc: blocked={'type':type(exc).__name__,'message':str(exc)}
            note=ws.agent_notifications(a)['notifications'][0]
            revalidated=ws.agent_revalidate_notification(a,note['id'])
            commit=ws.commit_change(txa['id'],a)
            verification=ws.verify(changed_paths=commit['changed_paths'])
            ws.policy_update({'source':{'approval':['billing/**']}})
            policy_plan=ws.change_plan([{'op':'replace_text','path':'billing/rules.py','old':'100','new':'120'}])
            approval=ws.approval_grant('edit',resource=None,granted_by='demo-reviewer')
            billtx=ws.stage_change([{'op':'replace_text','path':'billing/rules.py','old':'100','new':'120'}],approval_id=approval['id']); billcommit=ws.commit_change(billtx['id'])
            sym=ws.store.conn.execute("SELECT id FROM symbols WHERE name='validate_credentials'").fetchone()['id']
            inv=ws.invariant_create('Credential validation must accept present user identities',severity='critical')
            ws.invariant_link(inv['id'],'symbol',sym,relation='implements'); inv=ws.invariant_link(inv['id'],'test','tests/test_auth.py',relation='verifier')
            deps=ws.dependencies_world(); git={'status':ws.git_status(),'branches':ws.git_branches(),'impact':ws.git_commit_impact('HEAD'),'diff':ws.git_diff()}
            retention=ws.retention_compact({'max_acked_notifications':0},dry_run=True)
            report={
                'release':RELEASE,'world_before':world_before,'guidance':guidance,'state_security':state_security,'sandbox':sandbox,
                'context':{'confidence':ctx.decision_packet.get('retrieval_confidence'),'handle':ctx.handle,'top_paths':[o.path for o in ctx.objects[:5]]},
                'coordination':{'blocked_before_revalidation':blocked,'revalidated':revalidated,'commit_status':commit['status'],'rebased_from_revision':commit.get('rebased_from_revision'),'rebased_onto_revision':commit.get('rebased_onto_revision')},
                'beliefs':{'shared':ws.hypothesis_status(h['id']),'agent_A':belief_a,'agent_B':belief_b},
                'verification_status':verification['receipt'].get('structured',{}).get('status'),
                'policy':{'plan':policy_plan,'approved_commit':billcommit['status']},'invariant':inv,'dependencies':deps,'git':git,'retention_dry_run':retention,
                'world_after':ws.world_summary(),
                'claim_boundary':'End-to-end alpha.10 substrate/governance/cognition demo. It is not a model-quality, AGI, production-sandbox, or calibrated-probability benchmark.'
            }
        finally:
            ws.close(); shutdown_runtime_services()
    text=json.dumps(report,indent=2,sort_keys=True,default=str)
    if args.out: Path(args.out).write_text(text,encoding='utf-8')
    print(text)
if __name__=='__main__': main()

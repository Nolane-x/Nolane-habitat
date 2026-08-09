#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, tempfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out'); args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='habitat-a9-demo-') as td:
        td=Path(td); root=td/'repo'; root.mkdir()
        subprocess.run(['git','init','-q',str(root)],check=True)
        subprocess.run(['git','-C',str(root),'config','user.email','demo@example.com'],check=True)
        subprocess.run(['git','-C',str(root),'config','user.name','Habitat Demo'],check=True)
        (root/'auth.py').write_text('def validate_credentials(user):\n    return bool(user)\n')
        (root/'service.py').write_text('from auth import validate_credentials\n\ndef login(user):\n    return validate_credentials(user)\n')
        (root/'tests').mkdir(); (root/'tests'/'test_auth.py').write_text('import unittest\nfrom auth import validate_credentials\nclass T(unittest.TestCase):\n def test_auth(self): self.assertTrue(validate_credentials("u"))\n')
        (root/'pyproject.toml').write_text('[project]\nname="demo"\nversion="0"\ndependencies=["requests>=2"]\n')
        subprocess.run(['git','-C',str(root),'add','.'],check=True); subprocess.run(['git','-C',str(root),'commit','-q','-m','initial auth policy'],check=True)
        ws=HabitatWorkspace.create(root,td/'habitat')
        try:
            a=ws.agent_open('agent-A')['id']; b=ws.agent_open('agent-B')['id']
            ctx=ws.orient('fix credential validation login',12,agent_id=a)
            target=ctx.objects[0].object_id
            ws.context_feedback(ctx.handle,[target],[],2.0,agent_id=a)
            tx=ws.stage_change([{'op':'replace_text','path':'auth.py','old':'return bool(user)','new':'return user is not None'}],agent_id=a)
            conflict=None
            try: ws.stage_change([{'op':'replace_text','path':'auth.py','old':'return bool(user)','new':'return False'}],agent_id=b)
            except Exception as exc: conflict={'type':type(exc).__name__,'message':str(exc)}
            commit=ws.commit_change(tx['id'],agent_id=a)
            verification=ws.verify(changed_paths=commit['changed_paths'])
            h=ws.hypothesis_create('credential validation rejected falsey-but-present users',prior_confidence=.45)
            if verification['evidence'].get('recorded_evidence_ids'):
                ws.hypothesis_link_evidence(h['id'],verification['evidence']['recorded_evidence_ids'][0],'against',1.0)
            git=ws.git_status(); hist=ws.git_history('auth.py',5); deps=ws.dependencies_snapshot(); sec=ws.execution_security()
            report={
                'version':'0.1.0-alpha.9','context':{'confidence':ctx.decision_packet.get('retrieval_confidence'),'agent_id':a,'top_object':target},
                'lease_conflict':conflict,'commit_status':commit['status'],'verification_status':verification['receipt'].get('structured',{}).get('status'),
                'git':{'dirty':git.get('dirty'),'history_count':hist.get('count')},'dependencies':deps,
                'execution_security':sec,'hypothesis':ws.hypothesis_status(h['id']),
                'agent_A':ws.agent_status(a),'agent_B':ws.agent_status(b),
            }
        finally: ws.close()
    if args.out: Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__': main()

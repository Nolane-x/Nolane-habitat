from __future__ import annotations
import argparse,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat import HabitatWorkspace, runtime_service_status, shutdown_runtime_services

RELEASE='0.1.0-alpha.8'

def build(root:Path):
    (root/'tests').mkdir(parents=True)
    (root/'auth.py').write_text(
        'def validate_credentials(user, password):\n'
        '    """credential validation login"""\n'
        '    return user == "admin" and password == "secret"\n\n'
        'def login(user, password):\n'
        '    return validate_credentials(user, password)\n',encoding='utf-8')
    (root/'billing.py').write_text('def calculate_invoice_tax(amount, rate):\n    """invoice tax billing"""\n    return amount * rate\n',encoding='utf-8')
    (root/'tests'/'test_auth.py').write_text(
        'import unittest\nfrom auth import validate_credentials\n\n'
        'class AuthTest(unittest.TestCase):\n'
        '    def test_valid(self):\n        self.assertTrue(validate_credentials("admin", "secret"))\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); authority=base/'project'; authority.mkdir(); build(authority)
        t=time.perf_counter(); ws=HabitatWorkspace.create(authority,base/'habitat',backend='mirror'); cold=round((time.perf_counter()-t)*1000,2)
        backend=ws.backend_info()
        explored=ws.explore('change credential validation login and verify',line_budget=12,max_regions=4,context_budget=12)
        ctx_handle=explored['context_handle']
        plan=ws.context_plan_next(ctx_handle,max_pages=2,max_estimated_bytes=5000)
        fetched=ws.context_fetch_pages(ctx_handle,plan.get('page_ids',[]),5000)
        target=next(s for s in ws.store.all_symbols() if s['path']=='auth.py' and s['name']=='validate_credentials')
        ws.context_feedback(ctx_handle,[target['id']],[],1.0)
        efficiency_before=ws.context_efficiency(ctx_handle)
        episode=ws.episode_start('change credential validation login and verify',ctx_handle)
        body=ws.inspect(target['id'],'body')['source']
        tx=ws.stage_symbol_change(target['id'],body.replace('password == "secret"','password in {"secret", "backup"}'),episode['id'])
        commit=ws.commit_change(tx['id'])
        verify=ws.verify(changed_paths=commit['changed_paths'],timeout_s=30,episode_id=episode['id'])
        finished=ws.episode_finish(episode['id'],'completed',{'verification':'passed'})
        graph=ws.causality_graph(ctx_handle,max_depth=6,max_edges=100)
        ep_eff=ws.episode_efficiency(episode['id'])
        checkpoint=ws.checkpoint('continue credential hardening',next_action='review evidence',episode_id=None)
        resume=ws.resume(checkpoint['id'])
        no_gold=ws.explore('quantum banana teleportation matrix',line_budget=20,max_regions=4,context_budget=8)
        warm=ws.refresh('alpha7-demo-warm')
        auth_root=Path(backend['authoritative_root']); mirror_root=Path(backend['materialized_root'])
        receipt=verify['receipt']
        runtime_before=runtime_service_status()
        ws.close(); cleanup=shutdown_runtime_services(); runtime_after=runtime_service_status()
        report={
            'release':RELEASE,'cold_ingest_ms':cold,'backend':backend,
            'exploration':{
                'confidence':explored['retrieval_confidence'],'regions':explored['regions'],'lines_selected':explored['lines_selected'],
                'source_bytes_read':explored['source_bytes_read'],'page_plan':plan,'faulted_source_bytes':fetched['source_bytes'],
                'context_efficiency':efficiency_before,
            },
            'mutation':{
                'changed_paths':commit['changed_paths'],'authority_mirror_equal':(auth_root/'auth.py').read_bytes()==(mirror_root/'auth.py').read_bytes(),
                'contains_backup':b'"backup"' in (auth_root/'auth.py').read_bytes(),
            },
            'verification':{
                'status':(receipt.get('structured') or {}).get('status'),'exit_code':receipt['exit_code'],
                'source_authority_id':receipt.get('source_authority_id'),'execution_provider_id':receipt.get('execution_provider_id'),
                'execution_backend':receipt.get('execution_backend'),
            },
            'causal_work':{
                'episode_status':finished['status'],'edge_count':graph['edge_count'],'relations':sorted({e['relation'] for e in graph['edges']}),
                'episode_efficiency':ep_eff,
            },
            'checkpoint':{'resume_mode':resume['resume_mode'],'authority_drift':resume['source_authority_identity_drift'],'executor_drift':resume['execution_provider_identity_drift']},
            'no_gold':{'abstained':no_gold['abstained'],'confidence':no_gold['retrieval_confidence'],'source_bytes_read':no_gold['source_bytes_read']},
            'warm_refresh':warm,
            'runtime_lifecycle':{'before_shutdown':runtime_before,'shutdown':cleanup,'after_shutdown':runtime_after},
            'claim_boundary':'Executable alpha.7 substrate/explorer/context/provenance demo. It does not establish model token savings, coding superiority, Cloudflare compatibility, or AGI capability.'
        }
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

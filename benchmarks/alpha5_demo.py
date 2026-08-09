from __future__ import annotations
import argparse, json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat.protocol import HabitatProtocol
from habitat.mcp_adapter import tool_catalog


def build(root:Path):
    (root/'tests').mkdir(parents=True)
    (root/'auth.py').write_text('def validate_credentials(email, password):\n    return bool(email) and password == "secret"\n',encoding='utf-8')
    (root/'service.py').write_text('from auth import validate_credentials as check\n\ndef login(e,p):\n    return check(e,p)\n',encoding='utf-8')
    (root/'tests'/'test_auth.py').write_text('from auth import validate_credentials\n\ndef test_ok():\n    assert validate_credentials("a","secret")\n',encoding='utf-8')
    (root/'a.ts').write_text('export function value(){ return 1 }\n',encoding='utf-8')
    (root/'b.ts').write_text("import {value} from './a'; export function use(){ return value() }\n",encoding='utf-8')
    (root/'index.html').write_text('''<!doctype html><input id="name"><button id="go">Go</button><output id="out"></output>
<script>document.getElementById('go').addEventListener('click',()=>{document.getElementById('out').textContent='Hello '+document.getElementById('name').value})</script>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); project=base/'project'; project.mkdir(); build(project)
        t=time.perf_counter(); ws=HabitatWorkspace.create(project,base/'habitat'); cold_ms=round((time.perf_counter()-t)*1000,2)
        proto=HabitatProtocol(ws); start_rev=ws.revision
        ctx=ws.orient('fix credential validation login',budget=10)
        addr=ws.context_address_space(ctx.handle,50)
        prefetch=ws.context_prefetch(ctx.handle,max_source_bytes=5000,max_pages=6)
        nogold=ws.orient('quantum banana teleportation matrix',budget=8)

        target=next(s for s in ws.store.all_symbols() if s['path']=='auth.py' and s['name']=='validate_credentials')
        rename=ws.stage_symbol_rename(target['id'],'verify_credentials')
        rename_commit=ws.commit_change(rename['id'])
        rename_verify=ws.verify(changed_paths=rename_commit['changed_paths'],timeout_s=30)

        renamed=next(s for s in ws.store.all_symbols() if s['path']=='auth.py' and s['name']=='verify_credentials')
        broken=ws.stage_symbol_change(renamed['id'],'def verify_credentials(email, password):\n    return False')
        broken_commit=ws.commit_change(broken['id'])
        failed=ws.verify(changed_paths=broken_commit['changed_paths'],timeout_s=30)
        active_after_fail=ws.evidence_active('test-failure')
        current=next(s for s in ws.store.all_symbols() if s['path']=='auth.py' and s['name']=='verify_credentials')
        fixed=ws.stage_symbol_change(current['id'],'def verify_credentials(email, password):\n    return bool(email) and password == "secret"')
        fixed_commit=ws.commit_change(fixed['id'])
        passed=ws.verify(changed_paths=fixed_commit['changed_paths'],timeout_s=30)
        active_after_pass=ws.evidence_active('test-failure')

        merkle=ws.state_merkle_diff(start_rev,ws.revision)
        ui={'available':False}
        try:
            obs=ws.open_ui_runtime('index.html'); sid=obs['session_id']
            name=next(e['handle'] for e in obs['elements'] if e.get('attrs',{}).get('id')=='name')
            go=next(e['handle'] for e in obs['elements'] if e.get('attrs',{}).get('id')=='go')
            ws.act_ui_runtime(sid,'fill',name,'Nolane'); ws.act_ui_runtime(sid,'click',go)
            assertion=ws.assert_ui_runtime(sid,[{'role':'status','text_contains':'Hello Nolane','min_count':1}])
            # output role varies by browser accessibility; fall back to exact handle assertion when necessary.
            if not assertion['passed']:
                out=next(e['handle'] for e in ws.observe_ui_runtime(sid)['elements'] if e.get('attrs',{}).get('id')=='out')
                assertion=ws.assert_ui_runtime(sid,[{'handle':out,'text_contains':'Hello Nolane'}])
            ui={'available':True,'assertion':assertion}
        except Exception as exc:
            ui={'available':False,'reason':f'{type(exc).__name__}: {exc}'}

        warm=ws.refresh('alpha5-demo-warm')
        providers=ws.semantic_provider_report()
        checkpoint=ws.checkpoint('continue auth hardening',next_action='inspect verification evidence')
        resume=ws.resume(checkpoint['id'])
        report={
            'release':'0.1.0-alpha.5','cold_ingest_ms':cold_ms,
            'context':{'confidence':ctx.decision_packet.get('retrieval_confidence'),'objects':[o.__dict__ for o in ctx.objects],
                       'address_pages':len(addr['pages']),'prefetch_source_bytes':prefetch['source_bytes']},
            'selective_retrieval':{'no_gold_confidence':nogold.decision_packet.get('retrieval_confidence'),
                                   'abstention_recommended':nogold.decision_packet.get('abstention_recommended')},
            'semantic_rename':{'proposal':rename.get('semantic_rename'),'changed_paths':rename_commit['changed_paths'],
                               'verification_status':rename_verify['receipt']['structured']['status']},
            'evidence_lifecycle':{'failed_status':failed['receipt']['structured']['status'],'active_after_fail':active_after_fail['count'],
                                  'passed_status':passed['receipt']['structured']['status'],'active_after_pass':active_after_pass['count']},
            'merkle_diff':merkle,'ui':ui,'warm_refresh':warm,'providers':providers,'checkpoint_resume':{'mode':resume.get('resume_mode') or resume.get('mode')},
            'mcp':{'spec_target':'2026-07-28','tool_count':len(tool_catalog()),'tools':[x['name'] for x in tool_catalog()]},
            'claim_boundary':'Executable alpha.5 plumbing demo. It does not establish model token savings, coding superiority, or AGI capability.'
        }
        ws.close()
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

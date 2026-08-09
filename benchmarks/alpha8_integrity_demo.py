from __future__ import annotations
import argparse, json, os, stat, sys, tempfile, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat import HabitatWorkspace, shutdown_runtime_services

RELEASE='0.1.0-alpha.8'

def build(root: Path):
    (root/'tests').mkdir(parents=True)
    # Large source demonstrates sparse authority I/O. Target is near EOF but still parser-visible.
    filler=''.join(f'noise_{i} = "'+('x'*72)+'"\n' for i in range(12000))
    (root/'big.py').write_text(filler+'\ndef validate_credentials(user, password):\n    return user == "admin" and password == "secret"\n',encoding='utf-8')
    (root/'auth.py').write_text('def login(user, password):\n    return user == "admin" and password == "secret"\n',encoding='utf-8')
    (root/'tests'/'test_auth.py').write_text(
        'import unittest\nfrom auth import login\n\nclass T(unittest.TestCase):\n    def test_login(self):\n        self.assertTrue(login("admin", "secret"))\n',encoding='utf-8')
    script=root/'script.py'; script.write_bytes(b'def f():\r\n    return 1\r\n'); os.chmod(script,0o755)
    (root/'.gitignore').write_text('secret.yaml\n',encoding='utf-8')
    (root/'secret.yaml').write_text('API_KEY=DO_NOT_INDEX\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); project=base/'project'; project.mkdir(); build(project)
        t=time.perf_counter(); ws=HabitatWorkspace.create(project,base/'habitat'); cold=round((time.perf_counter()-t)*1000,2)
        # Perception-integrity probe: same byte length, restored mtime must still be admitted.
        auth=project/'auth.py'; st=auth.stat(); rev0=ws.revision
        auth.write_text('def login(user, password):\n    return user == "admin" and password == "public"\n',encoding='utf-8')
        os.utime(auth,ns=(st.st_atime_ns,st.st_mtime_ns)); rec=ws.reconcile(); rev1=ws.revision
        # Restore valid behavior through a transaction and verify.
        sym=next(s for s in ws.store.all_symbols() if s['path']=='auth.py' and s['name']=='login')
        body=ws.inspect(sym['id'],'body')['source']; tx=ws.stage_symbol_change(sym['id'],body.replace('"public"','"secret"')); commit=ws.commit_change(tx['id'])
        verification=ws.verify(changed_paths=commit['changed_paths'],timeout_s=30)
        # Sparse page fault on the >1MB file.
        big=next(s for s in ws.store.all_symbols() if s['path']=='big.py' and s['name']=='validate_credentials')
        big_ctx=ws.orient('validate credentials implementation',12)
        page=next(p for p in ws.context_address_space(big_ctx.handle)['pages'] if p['object_id']==big['id'])
        fetched=ws.context_fetch_pages(big_ctx.handle,[page['page_id']],max_source_bytes=5000)
        exact=fetched['pages'][0]
        # Mutation fidelity: CRLF + executable bit survive.
        before_mode=stat.S_IMODE((project/'script.py').stat().st_mode); before_crlf=b'\r\n' in (project/'script.py').read_bytes()
        tx2=ws.stage_change([{'op':'replace_text','path':'script.py','old':'return 1','new':'return 2'}]); ws.commit_change(tx2['id'])
        after_mode=stat.S_IMODE((project/'script.py').stat().st_mode); after_bytes=(project/'script.py').read_bytes()
        # Hypothesis/experiment loop.
        ctx=ws.orient('login credential authorization failure',10); ep=ws.episode_start('debug login authorization',ctx.handle)
        hyp=ws.hypothesis_create('credential policy mismatch causes login failure',episode_id=ep['id'],prior_confidence=0.35)
        exp=ws.experiment_plan('run targeted authentication tests after restoring credential policy',hypothesis_id=hyp['id'],discriminator='tests pass after credential policy restoration',capability='python.unittest')
        done=ws.experiment_complete(exp['id'],{'verification_status':(verification['receipt'].get('structured') or {}).get('status')},'completed')
        hyp2=ws.hypothesis_update(hyp['id'],status='supported',confidence=0.70,reason='discriminating verification matched expected behavior')
        ng=ws.explore('quantum banana teleportation matrix',line_budget=30,max_regions=5,context_budget=8)
        secret_indexed=ws.store.file_by_path('secret.yaml') is not None
        report={
            'release':RELEASE,'cold_ingest_ms':cold,
            'perception_integrity':{'old_revision':rev0,'new_revision':rev1,'detected_paths':rec['changed_paths'],'same_size_restored_mtime_detected':'auth.py' in rec['changed_paths']},
            'sparse_context_io':{'file_size_bytes':(project/'big.py').stat().st_size,'agent_visible_source_bytes':exact.get('actual_source_bytes',fetched.get('agent_visible_source_bytes')),'backend_authority_bytes_read':exact.get('backend_authority_bytes_read'),'io_mode':exact.get('io_mode'),'source_preview':exact.get('source','')[:160]},
            'mutation_fidelity':{'crlf_before':before_crlf,'crlf_after':b'\r\n' in after_bytes,'mode_before':oct(before_mode),'mode_after':oct(after_mode),'logic_updated':b'return 2' in after_bytes},
            'verification':{'status':(verification['receipt'].get('structured') or {}).get('status'),'exit_code':verification['receipt']['exit_code'],'environment_fingerprint':verification['receipt'].get('environment_fingerprint')},
            'source_policy':{'gitignored_secret_indexed':secret_indexed},
            'hypothesis_loop':{'hypothesis_status':hyp2['status'],'confidence':hyp2['current_confidence'],'confidence_semantics':hyp2['confidence_semantics'],'experiment_status':done['status']},
            'no_gold':{'confidence':ng['retrieval_confidence'],'abstained':ng['abstained'],'source_bytes_read':ng['source_bytes_read']},
            'claim_boundary':'Alpha.8 integrity/I-O/cognition mechanism evidence. Agent-visible bytes and authority bytes are separate; neither is a token count. Local execution remains explicitly unsandboxed.'
        }
        ws.close(); shutdown_runtime_services()
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

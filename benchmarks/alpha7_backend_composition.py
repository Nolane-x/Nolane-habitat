from __future__ import annotations
import argparse,json,shutil,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat.backends.local import DirectoryMirrorSourceAuthority, LocalExecutionProvider, CompositeProjectBackend

RELEASE='0.1.0-alpha.8'

def build(root:Path):
    (root/'tests').mkdir(parents=True)
    (root/'auth.py').write_text('def validate_credentials(x):\n    return bool(x)\n',encoding='utf-8')
    (root/'tests'/'test_auth.py').write_text('import unittest\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n',encoding='utf-8')

def sig(ws):
    return {
      'symbols':sorted((s['path'],s['qualified_name'],s['kind'],s['trust']) for s in ws.store.all_symbols()),
      'relations':sorted((r['source_id'],r['target_id'],r['kind'],r['trust']) for r in ws.store.conn.execute('SELECT source_id,target_id,kind,trust FROM relations')),
    }

def case(project:Path,h:Path,backend:str):
    with HabitatWorkspace.create(project,h,backend=backend) as ws:
        ctx=ws.explore('credential validation',line_budget=8,max_regions=3)
        return {'signature':sig(ws),'paths':[r['path'] for r in ctx['regions']],'confidence':ctx['retrieval_confidence'],'backend':ws.backend_info()}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); seed=base/'seed'; seed.mkdir(); build(seed)
        lp=base/'local'; mp=base/'mirror'; shutil.copytree(seed,lp); shutil.copytree(seed,mp)
        local=case(lp,base/'h-local','local'); mirror=case(mp,base/'h-mirror','mirror')
        authority=base/'authority'; execution=base/'execution'; material=base/'material'; shutil.copytree(seed,authority); shutil.copytree(seed,execution)
        source=DirectoryMirrorSourceAuthority(authority,material); executor=LocalExecutionProvider(execution,kind='sandbox-local')
        composed=CompositeProjectBackend(source,executor)
        caps=executor.discover_capabilities(); cap=next((c for c in caps if c['id']=='python.unittest'),None)
        fail_closed=None
        if cap:
            # force a source mutation to prove a detached execution checkout cannot silently become authority
            import sys as _sys
            mut={'id':'probe.mutate','kind':'script','argv':[_sys.executable,'-c','from pathlib import Path; Path("auth.py").write_text("def validate_credentials(x):\\n    return False\\n")']}
            try: composed.run(mut,20)
            except Exception as exc: fail_closed={'type':type(exc).__name__,'message':str(exc)}
        report={
          'release':RELEASE,'local_mirror_semantic_equal':local['signature']==mirror['signature'],
          'local_mirror_exploration_equal':local['paths']==mirror['paths'] and local['confidence']==mirror['confidence'],
          'local_backend':local['backend'],'mirror_backend':mirror['backend'],
          'detached_executor_mutation_fail_closed':bool(fail_closed and 'non-authoritative checkout' in fail_closed['message']),
          'fail_closed_error':fail_closed,
          'authority_unchanged':(authority/'auth.py').read_text(encoding='utf-8')==(seed/'auth.py').read_text(encoding='utf-8'),
          'claim_boundary':'Local/directory contract-double composition only; no real Cloudflare Computer transport or remote runtime is claimed.'
        }
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

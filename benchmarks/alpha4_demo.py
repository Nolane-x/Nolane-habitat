from __future__ import annotations
import argparse, json, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace


def build(root: Path):
    (root/'tests').mkdir(parents=True)
    (root/'auth.py').write_text('def validate_credentials(email, password):\n    return bool(email) and password == "secret"\n')
    (root/'service.py').write_text('from auth import validate_credentials\ndef login(e,p):\n    return validate_credentials(e,p)\n')
    (root/'tests'/'test_auth.py').write_text('import unittest\nfrom auth import validate_credentials\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(validate_credentials("a","secret"))\nif __name__ == "__main__": unittest.main()\n')
    (root/'index.html').write_text('<!doctype html><button id="save">Save</button>')
    (root/'App.tsx').write_text('export function App(){\n  function handleSave(){ return 1 }\n  return <button id="save" onClick={handleSave}>Save</button>\n}\n')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); project=base/'project'; project.mkdir(); build(project)
        ws=HabitatWorkspace.create(project,base/'habitat'); proto=HabitatProtocol(ws)
        first=ws.orient('fix credential validation login',budget=8)
        residency=ws.residency_configure(4,20000); admitted=ws.residency_admit(first.handle,pin_top=1)
        resident_packet=ws.residency_materialize(max_source_bytes=5000,max_objects=4)
        proto.handle({'id':'ts','method':'workspace.trace.start','params':{'label':'alpha4-related-followup'}})
        follow=proto.handle({'id':'o','method':'workspace.orient','params':{'task':'review credential validation behavior','budget':8}})['result']
        follow_packet=proto.handle({'id':'m','method':'workspace.context.materialize','params':{'handle':follow['handle'],'max_source_bytes':5000}})['result']
        trace=proto.handle({'id':'te','method':'workspace.trace.stop','params':{}})['result']
        target=next(s for s in ws.store.all_symbols() if s['path']=='auth.py' and s['name']=='validate_credentials')
        staged=ws.stage_symbol_change(target['id'],'def validate_credentials(email, password):\n    return bool(email) and password in {"secret", "better"}')
        committed=ws.commit_change(staged['id'])
        resident_after=ws.residency_status()
        refreshed=ws.context_refresh(first.handle,budget=8)
        ws.residency_evict(stale_only=True)
        ws.residency_admit(refreshed['context']['handle'],pin_top=1)
        verification=ws.verify(object_ids=[target['id']],timeout_s=30)
        ui={'available':False}
        try:
            obs=ws.open_ui_runtime('index.html')
            button=next(e for e in obs['elements'] if e.get('attrs',{}).get('id')=='save')
            ui={'available':True,'source_hints':button.get('source_hints',[]),'handler_hints':[h for h in button.get('source_hints',[]) if h['relation'].startswith('framework-event-handler:')]}
        except Exception as exc:
            ui={'available':False,'reason':f'{type(exc).__name__}: {exc}'}
        warm=ws.refresh('alpha4-demo-warm')
        report={
            'release':'0.1.0-alpha.4','first_context':{'handle':first.handle,'objects':[o.__dict__ for o in first.objects]},
            'residency':{'configure':residency,'admit':{'admitted':admitted['admitted'],'status':admitted['status']},'materialized':resident_packet,'after_mutation':resident_after},
            'trace':trace,'followup_context':follow,'followup_materialization':{'source_bytes':follow_packet['source_bytes'],'object_count':follow_packet['object_count']},
            'mutation':{'transaction':committed['id'],'revision':committed['committed_revision'],'semantic_diff':committed.get('semantic_diff')},
            'context_refresh_delta':refreshed['delta'],'verification':{'exit_code':verification['receipt']['exit_code'],'selection':verification['receipt'].get('structured',{}).get('selection')},
            'ui':ui,'warm_refresh':warm,
            'claim_boundary':'Demonstrates alpha.4 plumbing and invariants only; it is not an LLM capability or token-efficiency benchmark.'
        }
        ws.close()
    text=json.dumps(report,indent=2,ensure_ascii=False)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)

if __name__=='__main__': main()

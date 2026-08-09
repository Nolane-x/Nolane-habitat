from __future__ import annotations
import argparse, json, tempfile, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat.ui import BrowserRuntime


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output'); args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); p=root/'project'; p.mkdir(); (p/'tests').mkdir()
        (p/'auth.py').write_text('def validate_credentials(email, password):\n    return password == "secret"\n')
        (p/'other.py').write_text('def validate_credentials(email, password):\n    return False\n')
        (p/'service.py').write_text('import auth\n\ndef login(email,password):\n    return auth.validate_credentials(email,password)\n')
        (p/'tests'/'test_auth.py').write_text('import unittest\nimport service\nclass AuthTest(unittest.TestCase):\n    def test_login(self): self.assertTrue(service.login("a","secret"))\n')
        (p/'tests'/'test_other.py').write_text('import unittest\nimport other\nclass OtherTest(unittest.TestCase):\n    def test_other(self): self.assertFalse(other.validate_credentials("a","x"))\n')
        (p/'index.html').write_text('<label for="name">Name</label><input id="name"><button data-testid="go">Go</button><div id="out" role="status"></div><script src="app.js"></script>')
        (p/'app.js').write_text("document.querySelector('[data-testid=go]').addEventListener('click',()=>document.getElementById('out').textContent='Hello '+document.getElementById('name').value)\n")
        t=time.perf_counter(); ws=HabitatWorkspace.create(p,root/'habitat'); cold_ms=round((time.perf_counter()-t)*1000,2)
        enter=ws.enter(); ctx=ws.orient('fix credential validation and verify login behavior',budget=8)
        target=next(x for x in ws.store.all_symbols() if x['path']=='auth.py' and x['name']=='validate_credentials')
        refs=ws.references(target['id']); impact=ws.impact(object_ids=[target['id']]); verification=ws.verify(object_ids=[target['id']],timeout_s=20)
        cursor=ws.store.latest_event_seq()
        tx=ws.stage_symbol_change(target['id'],'def validate_credentials(email, password):\n    return password in {"secret", "better"}')
        committed=ws.commit_change(tx['id'])
        events=ws.events_poll(cursor,reconcile=False)
        ui=None
        if BrowserRuntime.probe()['available']:
            opened=ws.open_ui_runtime('index.html'); sid=opened['session_id']
            inp=next(e for e in opened['elements'] if e['attrs'].get('id')=='name')
            btn=next(e for e in opened['elements'] if e['attrs'].get('data-testid')=='go')
            ws.act_ui_runtime(sid,'fill',inp['handle'],'Nolane')
            acted=ws.act_ui_runtime(sid,'click',btn['handle'])
            out=next(e for e in acted['elements'] if e['attrs'].get('id')=='out')
            ui={'output_text':out['text'],'button_source_hints':btn.get('source_hints',[]),'delta':acted['delta']}
            ws.close_ui_runtime(sid)
        warm=ws.refresh('alpha2-demo-noop')
        result={
          'release':'0.1.0-alpha.2','cold_ingest_ms':cold_ms,'enter':enter,
          'context':{'task_class':ctx.task_class,'objects':[o.__dict__ for o in ctx.objects],'trust_counts':ctx.trust_counts,'decision_packet':ctx.decision_packet},
          'references_to_auth_validate':refs,'impact':impact,'verification':verification,
          'transaction':{'status':committed['status'],'semantic_diff':committed['semantic_diff']},
          'events_after_commit':events,'ui':ui,'warm_refresh':warm,
          'claim_boundary':'Executable demo evidence only; no LLM token-savings or universal correctness claim.'
        }
        ws.close()
    text=json.dumps(result,indent=2)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

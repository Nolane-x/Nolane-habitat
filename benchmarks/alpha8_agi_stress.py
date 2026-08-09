from __future__ import annotations
import argparse,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat import shutdown_runtime_services
RELEASE='0.1.0-alpha.8'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('source_zip'); ap.add_argument('--output'); args=ap.parse_args(); src=Path(args.source_zip).resolve()
    with tempfile.TemporaryDirectory() as td:
        h=Path(td)/'habitat'; t=time.perf_counter(); ws=HabitatWorkspace.create(src,h); cold=round((time.perf_counter()-t)*1000,2)
        enter=ws.enter(); coldp=ws.semantic_provider_report(); t=time.perf_counter(); ordinary=ws.reconcile(); ordinary_ms=round((time.perf_counter()-t)*1000,2); t=time.perf_counter(); warm=ws.refresh('alpha8-stress-deep-scrub'); warm_ms=round((time.perf_counter()-t)*1000,2)
        exp=ws.explore('context engineering tool orchestration semantic proof',line_budget=80,max_regions=10,context_budget=16)
        plan=ws.context_plan_next(exp['context_handle'],max_pages=4,max_estimated_bytes=8000)
        fetched=ws.context_fetch_pages(exp['context_handle'],plan.get('page_ids',[]),8000)
        eff=ws.context_efficiency(exp['context_handle'])
        ng=ws.explore('quantum banana teleportation matrix',line_budget=40,max_regions=6,context_budget=8)
        live=ws.semantic_provider_report()
        # A Unicode query proves the tokenizer does not shatter non-ASCII text, even if this corpus has no gold.
        vi=ws.explore('xác thực người dùng và quyền truy cập',line_budget=40,max_regions=6,context_budget=8)
        report={'release':RELEASE,'corpus':src.name,'cold_ingest_ms':cold,'warm_refresh_ms':warm_ms,
                'file_count':enter['file_count'],'symbol_count':enter['symbol_count'],'occurrence_count':enter['occurrence_count'],
                'providers_cold':coldp,'providers_warm':live,'ordinary_reconcile':ordinary,'ordinary_reconcile_ms':ordinary_ms,'deep_refresh':warm,
                'explorer':{'confidence':exp['retrieval_confidence'],'region_count':exp['region_count'],'lines_selected':exp['lines_selected'],'paths':[r['path'] for r in exp['regions']],
                            'source_bytes_read':exp['source_bytes_read'],'agent_visible_source_bytes':fetched.get('agent_visible_source_bytes',fetched.get('source_bytes',0)),
                            'backend_authority_bytes_read':fetched.get('backend_authority_bytes_read',0),'efficiency':eff},
                'no_gold':{'confidence':ng['retrieval_confidence'],'abstained':ng['abstained'],'region_count':ng['region_count'],'source_bytes_read':ng['source_bytes_read']},
                'unicode_query':{'confidence':vi['retrieval_confidence'],'abstained':vi['abstained'],'region_count':vi['region_count']},
                'claim_boundary':'Measures deterministic alpha.8 integrity/index/compiler/explorer/I-O plumbing on supplied corpus; not an LLM/token/AGI benchmark. Authority I/O and model-visible source bytes are separate metrics.'}
        ws.close(); shutdown_runtime_services()
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

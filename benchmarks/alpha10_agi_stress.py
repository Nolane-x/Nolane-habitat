#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat import shutdown_runtime_services
RELEASE='0.1.0-alpha.10'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('source_zip'); ap.add_argument('--output'); args=ap.parse_args(); src=Path(args.source_zip).resolve()
    with tempfile.TemporaryDirectory() as td:
        h=Path(td)/'habitat'; t=time.perf_counter(); ws=HabitatWorkspace.create(src,h); cold=round((time.perf_counter()-t)*1000,2)
        enter=ws.enter(); providers_cold=ws.semantic_provider_report(); t=time.perf_counter(); ordinary=ws.reconcile(); ordinary_ms=round((time.perf_counter()-t)*1000,2)
        exp=ws.explore('context engineering tool orchestration semantic proof',line_budget=80,max_regions=10,context_budget=16)
        plan=ws.context_plan_next(exp['context_handle'],max_pages=4,max_estimated_bytes=8000); fetched=ws.context_fetch_pages(exp['context_handle'],plan.get('page_ids',[]),8000)
        ng=ws.explore('quantum banana teleportation matrix',line_budget=40,max_regions=6,context_budget=8)
        t=time.perf_counter(); deep=ws.refresh('alpha10-explicit-deep-scrub'); deep_ms=round((time.perf_counter()-t)*1000,2)
        providers_warm=ws.semantic_provider_report(); world=ws.world_summary(); sec=ws.state_security(); sandbox=ws.sandbox_status()
        report={'release':RELEASE,'corpus':src.name,'cold_ingest_ms':cold,'file_count':enter['file_count'],'symbol_count':enter['symbol_count'],'occurrence_count':enter['occurrence_count'],
                'ordinary_reconcile':ordinary,'ordinary_reconcile_ms':ordinary_ms,'deep_refresh':deep,'deep_refresh_ms':deep_ms,
                'providers_cold':providers_cold,'providers_warm':providers_warm,
                'explorer':{'confidence':exp['retrieval_confidence'],'regions':exp['region_count'],'lines':exp['lines_selected'],'paths':[r['path'] for r in exp['regions']],
                            'agent_visible_source_bytes':fetched.get('agent_visible_source_bytes',fetched.get('source_bytes',0)),'backend_authority_bytes_read':fetched.get('backend_authority_bytes_read',0)},
                'no_gold':{'confidence':ng['retrieval_confidence'],'abstained':ng['abstained'],'source_bytes_read':ng['source_bytes_read']},
                'world_summary':world,'state_security':sec,'sandbox':sandbox,
                'claim_boundary':'Deterministic alpha.10 compiler/retrieval/governance/I-O plumbing stress on supplied corpus; not an LLM/token/AGI or production-security benchmark.'}
        ws.close(); shutdown_runtime_services()
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat import shutdown_runtime_services
RELEASE='0.1.0-alpha.11'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('source_zip'); ap.add_argument('--output'); args=ap.parse_args(); src=Path(args.source_zip).resolve()
    with tempfile.TemporaryDirectory() as td:
        h=Path(td)/'habitat'; t=time.perf_counter(); ws=HabitatWorkspace.create(src,h); cold=round((time.perf_counter()-t)*1000,2)
        enter=ws.enter(); providers_cold=ws.semantic_provider_report(); fabric=ws.semantic_fabric()
        t=time.perf_counter(); ordinary=ws.reconcile(); ordinary_ms=round((time.perf_counter()-t)*1000,2)
        aid=ws.agent_open('alpha11-stress-agent',{'surface':'benchmark'})['id']
        exp=ws.explore('context engineering tool orchestration semantic proof',line_budget=80,max_regions=10,context_budget=16,agent_id=aid)
        plan=ws.context_plan_next(exp['context_handle'],max_pages=4,max_estimated_bytes=8000); fetched=ws.context_fetch_pages(exp['context_handle'],plan.get('page_ids',[]),8000)
        mem=ws.memory_record('episodic','Alpha11 stress explored the supplied AGI corpus with bounded source paging',agent_id=aid,confidence=.9,provenance={'corpus':src.name,'context_handle':exp['context_handle']})
        recalled=ws.memory_recall('bounded source paging',agent_id=aid)
        ng=ws.explore('quantum banana teleportation matrix',line_budget=40,max_regions=6,context_budget=8,agent_id=aid)
        cognition=ws.cognition_next(aid)
        t=time.perf_counter(); deep=ws.refresh('alpha11-explicit-deep-scrub'); deep_ms=round((time.perf_counter()-t)*1000,2)
        providers_warm=ws.semantic_provider_report(); world=ws.world_summary(); activities=ws.activity_since(0,500)
        report={
            'release':RELEASE,'corpus':src.name,'cold_ingest_ms':cold,'file_count':enter['file_count'],'symbol_count':enter['symbol_count'],'occurrence_count':enter['occurrence_count'],
            'ordinary_reconcile':ordinary,'ordinary_reconcile_ms':ordinary_ms,'deep_refresh':deep,'deep_refresh_ms':deep_ms,
            'providers_cold':providers_cold,'providers_warm':providers_warm,'semantic_fabric':fabric,
            'explorer':{'confidence':exp['retrieval_confidence'],'regions':exp['region_count'],'lines':exp['lines_selected'],'paths':[r['path'] for r in exp['regions']],
                        'agent_visible_source_bytes':fetched.get('agent_visible_source_bytes',fetched.get('source_bytes',0)),'backend_authority_bytes_read':fetched.get('backend_authority_bytes_read',0)},
            'no_gold':{'confidence':ng['retrieval_confidence'],'abstained':ng['abstained'],'source_bytes_read':ng['source_bytes_read']},
            'project_memory':{'recorded_id':mem['id'],'recall_count':recalled['count'],'revision_drift_after_deep_scrub':ws.memory_status(mem['id'])['revision_drift']},
            'cognitive_next':cognition,'activity_events':len(activities['events']),'world_summary':world,
            'claim_boundary':'Deterministic alpha.11 compiler/retrieval/memory/activity/provider-fabric stress on the supplied corpus. It is not an LLM/token/AGI benchmark; discovered semantic providers are capabilities, not automatic proof they were used.'}
        ws.agent_close(aid); ws.close(); shutdown_runtime_services()
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

from __future__ import annotations
import argparse,json,tempfile,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('source_zip'); ap.add_argument('--output'); args=ap.parse_args(); src=Path(args.source_zip).resolve()
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); h=base/'habitat'
        t=time.perf_counter(); ws=HabitatWorkspace.create(src,h); cold_ms=round((time.perf_counter()-t)*1000,2)
        enter=ws.enter(); merkle=ws.state_merkle(); providers_cold=ws.semantic_provider_report()
        t=time.perf_counter(); warm=ws.refresh('alpha5-stress-warm'); warm_ms=round((time.perf_counter()-t)*1000,2)
        providers_warm=ws.semantic_provider_report()
        ctx=ws.orient('context engineering tool orchestration semantic proof',12)
        prefetch=ws.context_prefetch(ctx.handle,12000,8)
        nogold=ws.orient('quantum banana teleportation matrix',8)
        code=next((r for r in ws.store.all_files() if r['language']=='python' and r['size']<200000),None)
        code_probe=None
        if code:
            p=ws.resolve_source_path(code['path']); raw=p.read_bytes(); p.write_bytes(raw+b'\n')
            t=time.perf_counter(); changed=ws.reconcile(); elapsed=round((time.perf_counter()-t)*1000,2)
            code_probe={'path':code['path'],'elapsed_ms':elapsed,'refresh':changed,'python_jedi':ws.semantic_provider_report()['providers']['python-jedi']}
        report={'release':'0.1.0-alpha.5','corpus':src.name,'cold_ingest_ms':cold_ms,'warm_refresh_ms':warm_ms,
                'file_count':enter['file_count'],'symbol_count':enter['symbol_count'],'occurrence_count':enter['occurrence_count'],
                'source_bytes':enter['index_health']['source_bytes'],'indexed_bytes':enter['index_health']['indexed_bytes'],
                'merkle':{'root_hash':merkle['project_root_hash'],'file_count':merkle['snapshot']['file_count'],'source_bytes_read':merkle['source_bytes_read']},
                'providers_cold':providers_cold,'providers_warm':providers_warm,'warm_refresh':warm,
                'context':{'confidence':ctx.decision_packet.get('retrieval_confidence'),'object_count':len(ctx.objects),'prefetch_source_bytes':prefetch['source_bytes']},
                'no_gold':{'confidence':nogold.decision_packet.get('retrieval_confidence'),'abstain':nogold.decision_packet.get('abstention_recommended')},
                'python_edit_probe':code_probe,
                'claim_boundary':'Measures Habitat deterministic indexing/semantic/context plumbing on this corpus; it is not an LLM performance or token benchmark.'}
        ws.close()
    text=json.dumps(report,indent=2,ensure_ascii=False,default=str)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

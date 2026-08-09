from __future__ import annotations
import argparse, json, tempfile, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('source_zip'); ap.add_argument('--output'); args=ap.parse_args()
    src=Path(args.source_zip).resolve()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); h=root/'habitat'
        t=time.perf_counter(); ws=HabitatWorkspace.create(src,h); cold_ms=round((time.perf_counter()-t)*1000,2)
        enter=ws.enter(); db_size=(h/'habitat.sqlite3').stat().st_size
        t=time.perf_counter(); warm=ws.refresh('alpha3-stress-warm-noop'); warm_ms=round((time.perf_counter()-t)*1000,2)
        ctx=ws.orient('context engineering tool orchestration semantic proof',budget=12)

        # Documentation-only mutation should compile that file but reuse semantic provider domains.
        doc=next((r for r in ws.store.all_files() if r['language']=='markdown' and r['size']<200000),None)
        doc_probe=None
        if doc:
            path=ws.resolve_source_path(doc['path']); path.write_bytes(path.read_bytes()+b'\n')
            t=time.perf_counter(); changed=ws.reconcile(); elapsed=round((time.perf_counter()-t)*1000,2)
            doc_probe={'path':doc['path'],'elapsed_ms':elapsed,'refresh':changed}

        # A code mutation exercises targeted compilation + semantic graph delta.
        code=next((r for r in ws.store.all_files() if r['language']=='python' and r['size']<200000),None)
        code_probe=None
        if code:
            path=ws.resolve_source_path(code['path']); path.write_bytes(path.read_bytes()+b'\n')
            t=time.perf_counter(); changed=ws.reconcile(); elapsed=round((time.perf_counter()-t)*1000,2)
            code_probe={'path':code['path'],'elapsed_ms':elapsed,'refresh':changed}

        report={
          'release':'0.1.0-alpha.3','corpus':src.name,'cold_ingest_ms':cold_ms,'warm_refresh_ms':warm_ms,
          'source_bytes':enter['index_health']['source_bytes'],'indexed_bytes':enter['index_health']['indexed_bytes'],'sqlite_bytes':db_size,
          'file_count':enter['file_count'],'symbol_count':enter['symbol_count'],'occurrence_count':enter.get('occurrence_count'),
          'warm_refresh':warm,'documentation_probe':doc_probe,'code_probe':code_probe,
          'context':{'objects':[o.__dict__ for o in ctx.objects],'unknowns':ctx.unknowns,'trust_counts':ctx.trust_counts,'lane_counts':ctx.lane_counts},
          'provider_report':ws.semantic_provider_report(),
          'claim_boundary':'Measures Habitat indexing/synchronization plumbing on this corpus; it does not measure model tokens, coding success, or AGI capability.'
        }
        ws.close()
    text=json.dumps(report,indent=2)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

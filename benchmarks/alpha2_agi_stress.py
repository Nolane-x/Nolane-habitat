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
        t=time.perf_counter(); warm=ws.refresh('stress-warm-noop'); warm_ms=round((time.perf_counter()-t)*1000,2)
        ctx=ws.orient('context engineering tool orchestration semantic proof',budget=12)
        cursor=ws.store.latest_event_seq()
        candidate=next((r for r in ws.store.all_files() if r['language'] in {'python','markdown','json'} and r['size']<200000),None)
        mutation=None
        if candidate:
            path=ws.resolve_source_path(candidate['path']); before=path.read_bytes(); path.write_bytes(before+b'\n')
            t=time.perf_counter(); changed=ws.refresh('stress-one-file-external-edit'); change_ms=round((time.perf_counter()-t)*1000,2)
            mutation={'path':candidate['path'],'refresh_ms':change_ms,'refresh':changed}
        events=ws.events_poll(cursor,reconcile=False)
        report={
          'release':'0.1.0-alpha.2','corpus':src.name,'cold_ingest_ms':cold_ms,'warm_refresh_ms':warm_ms,
          'source_bytes':enter['index_health']['source_bytes'],'indexed_bytes':enter['index_health']['indexed_bytes'],'sqlite_bytes':db_size,
          'file_count':enter['file_count'],'symbol_count':enter['symbol_count'],'occurrence_count':enter.get('occurrence_count'),
          'cold_provider_summary':ws.store.load_project_cache('semantic-project-v2').get('providers',{}) if ws.store.load_project_cache('semantic-project-v2') else {},
          'warm_refresh':warm,'one_file_mutation':mutation,'events':events,
          'context':{'objects':[o.__dict__ for o in ctx.objects],'unknowns':ctx.unknowns,'trust_counts':ctx.trust_counts,'lane_counts':ctx.lane_counts},
          'provider_report':ws.semantic_provider_report(),
          'claim_boundary':'Measures Habitat plumbing on this corpus; it does not measure model token use, task success, or AGI capability.'
        }
        ws.close()
    text=json.dumps(report,indent=2)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    else: print(text)
if __name__=='__main__': main()

from __future__ import annotations
import argparse, json, tempfile, time
from pathlib import Path
from habitat.workspace import HabitatWorkspace
from habitat.model import to_dict

TASKS = [
    "understand context engineering and context packet construction",
    "find tool orchestration and execution proof logic",
    "locate semantic proof and verification policy",
]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("source"); ap.add_argument("--output"); a=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        work=Path(td)/"habitat"
        t=time.perf_counter(); ws=HabitatWorkspace.create(Path(a.source),work); cold=time.perf_counter()-t
        entered=ws.enter()
        t=time.perf_counter(); warm=ws.refresh("benchmark-warm"); warm_s=time.perf_counter()-t
        contexts=[]
        for task in TASKS:
            t=time.perf_counter(); ctx=ws.orient(task,12); elapsed=time.perf_counter()-t
            contexts.append({"task":task,"seconds":elapsed,"task_class":ctx.task_class,"objects":[to_dict(o) for o in ctx.objects[:6]],"omitted":ctx.omitted_candidates,"lane_counts":ctx.lane_counts})
        result={"source":str(a.source),"cold_ingest_seconds":cold,"warm_refresh_seconds":warm_s,"warm_refresh":warm,
                "workspace":{"file_count":entered["file_count"],"symbol_count":entered["symbol_count"],"diagnostic_count":entered["diagnostic_count"],"index_health":entered["index_health"]},
                "contexts":contexts,
                "claim_boundary":"This probe measures Habitat plumbing/index behavior only. It does not measure LLM token savings or task-success uplift."}
        text=json.dumps(result,indent=2,ensure_ascii=False)
        if a.output: Path(a.output).write_text(text,encoding="utf-8")
        print(text)
        ws.close()
if __name__=="__main__": main()

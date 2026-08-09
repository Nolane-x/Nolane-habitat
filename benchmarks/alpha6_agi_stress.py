from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from habitat.workspace import HabitatWorkspace


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("source_zip"); ap.add_argument("--output"); args = ap.parse_args()
    src = Path(args.source_zip).resolve()
    with tempfile.TemporaryDirectory() as td:
        base = Path(td); h = base / "habitat"
        t = time.perf_counter(); ws = HabitatWorkspace.create(src, h); cold_ms = round((time.perf_counter()-t)*1000, 2)
        enter = ws.enter(); providers_cold = ws.semantic_provider_report()
        t = time.perf_counter(); warm = ws.refresh("alpha6-stress-warm"); warm_ms = round((time.perf_counter()-t)*1000,2)
        ctx = ws.orient("context engineering tool orchestration semantic proof", 12)
        plan = ws.context_plan_next(ctx.handle, max_pages=4, max_estimated_bytes=8000)
        fetched = ws.context_fetch_pages(ctx.handle, plan.get("page_ids", []), 8000)
        selected = [x.object_id for x in ctx.objects[:2]]
        feedback = ws.context_feedback(ctx.handle, selected, [], 0.5) if selected else None
        follow = ws.orient("context engineering tool orchestration semantic proof", 12)
        nogold = ws.orient("quantum banana teleportation matrix", 8)
        nogold_plan = ws.context_plan_next(nogold.handle, max_pages=3, max_estimated_bytes=5000)
        report = {
            "release": "0.1.0-alpha.6", "corpus": src.name, "cold_ingest_ms": cold_ms, "warm_refresh_ms": warm_ms,
            "file_count": enter["file_count"], "symbol_count": enter["symbol_count"], "occurrence_count": enter["occurrence_count"],
            "backend": ws.backend_info(), "providers_cold": providers_cold, "providers_warm": ws.semantic_provider_report(),
            "warm_refresh": warm,
            "context": {"confidence": ctx.decision_packet.get("retrieval_confidence"), "planned_pages": plan.get("page_ids", []),
                        "source_bytes": fetched.get("source_bytes", 0), "feedback_recorded": bool(feedback),
                        "followup_confidence": follow.decision_packet.get("retrieval_confidence")},
            "no_gold": {"confidence": nogold.decision_packet.get("retrieval_confidence"),
                        "abstain": nogold.decision_packet.get("abstention_recommended"),
                        "page_plan_action": nogold_plan.get("action"), "source_bytes_read": nogold_plan.get("source_bytes_read")},
            "claim_boundary": "Measures deterministic alpha.6 workspace/backend/context plumbing on the supplied corpus; not an LLM/token/AGI benchmark.",
        }
        ws.close()
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.output: Path(args.output).write_text(text, encoding="utf-8")
    else: print(text)


if __name__ == "__main__": main()

"""Small deterministic benchmark seed; not an LLM/token benchmark."""
from __future__ import annotations
import json, tempfile, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from habitat.workspace import HabitatWorkspace
from habitat.util import iter_project_files


def run(project: Path) -> dict:
    with tempfile.TemporaryDirectory() as td:
        t0 = time.perf_counter(); ws = HabitatWorkspace.create(project, Path(td) / "h"); cold = time.perf_counter() - t0
        t1 = time.perf_counter(); ctx = ws.orient("where is login credential validation implemented", budget=8); warm = time.perf_counter() - t1
        returned_source_bytes = 0
        inspected = []
        for obj in ctx.objects[:3]:
            if obj.object_type == "symbol":
                value = ws.inspect(obj.object_id, "body")
                returned_source_bytes += len(value.get("source", "").encode())
                inspected.append(value.get("qualified_name"))
        direct_bytes = sum(p.stat().st_size for p in iter_project_files(project))
        return {
            "benchmark_kind": "plumbing-byte-proxy-only",
            "warning": "This does not measure LLM tokens or task success.",
            "cold_ingest_ms": round(cold * 1000, 3),
            "warm_orient_ms": round(warm * 1000, 3),
            "project_file_bytes": direct_bytes,
            "exact_source_bytes_returned_for_first_3_symbols": returned_source_bytes,
            "orientation_objects": len(ctx.objects),
            "inspected_symbols": inspected,
        }

if __name__ == "__main__":
    sample = Path(__file__).parents[1] / "examples" / "sample_project"
    print(json.dumps(run(sample), indent=2))

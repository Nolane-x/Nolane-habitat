from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from habitat.workspace import HabitatWorkspace


SCHEMA = "foundation-baseline.v1"
SUITE = "foundation-baseline"
DEFAULT_TASK = "map Habitat release identity and semantic foundation"


def _elapsed_ms(start_ns: int) -> int:
    return max(0, (time.perf_counter_ns() - start_ns) // 1_000_000)


def collect_baseline(repo: Path, task: str = DEFAULT_TASK) -> dict:
    """Collect one descriptive, non-gating Foundation Convergence baseline run.

    The collector intentionally uses Habitat's public workspace lifecycle for the measured
    operations. Timing values are observations from one host/run; they are not pass/fail
    thresholds and must not be interpreted as a superiority claim.
    """
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise NotADirectoryError(repo)
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    task = task.strip()

    with tempfile.TemporaryDirectory(prefix="habitat-foundation-baseline-") as td:
        habitat_dir = Path(td) / "workspace"
        start_ns = time.perf_counter_ns()
        ws = HabitatWorkspace.create(repo, habitat_dir)
        cold_ms = _elapsed_ms(start_ns)
        try:
            source = {
                "root": str(repo),
                "revision": ws.revision,
                "files": len(ws.store.all_files()),
                "symbols": len(ws.store.all_symbols()),
                "diagnostics": len(ws.store.all_diagnostics()),
            }

            start_ns = time.perf_counter_ns()
            warm = ws.reconcile()
            warm_ms = _elapsed_ms(start_ns)

            start_ns = time.perf_counter_ns()
            context = ws.orient(task, budget=18)
            orientation_ms = _elapsed_ms(start_ns)

            fabric = ws.semantic_fabric()
            sqlite_path = habitat_dir / "habitat.sqlite3"
            sqlite_bytes = sqlite_path.stat().st_size if sqlite_path.is_file() else 0

            return {
                "schema": SCHEMA,
                "suite": SUITE,
                "source": source,
                "cold_ingest": {
                    "wall_ms": cold_ms,
                },
                "warm_reconcile": {
                    "wall_ms": warm_ms,
                    "unchanged": bool(warm.get("unchanged")),
                    "changed_paths": list(warm.get("changed_paths") or []),
                    "refresh_mode": warm.get("refresh_mode"),
                    "hashed_files": int(warm.get("hashed_files") or 0),
                },
                "orientation": {
                    "task": context.task,
                    "wall_ms": orientation_ms,
                    "handle": context.handle,
                    "task_class": context.task_class,
                    "object_count": len(context.objects),
                    "unknown_count": len(context.unknowns),
                    "omitted_candidates": int(context.omitted_candidates),
                    "budget": int(context.budget),
                    "lane_counts": dict(context.lane_counts),
                    "trust_counts": dict(context.trust_counts),
                    "decision_packet": dict(context.decision_packet),
                },
                "semantic_fabric": fabric,
                "storage": {
                    "sqlite_bytes": int(sqlite_bytes),
                },
                "claim_boundary": (
                    "Descriptive single-run foundation evidence only. Timing and counts vary by host, "
                    "repository state, installed semantic providers, and cache state; this report is not "
                    "a performance threshold or a claim of superiority over another agent workflow."
                ),
            }
        finally:
            ws.close()


def _write_json_atomic(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    report = collect_baseline(args.repo, args.task)
    if args.out:
        _write_json_atomic(args.out, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

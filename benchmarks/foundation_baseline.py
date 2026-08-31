from __future__ import annotations

import argparse
import json
import os
import sys
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


def _unavailable_process_memory(method: str) -> dict[str, object]:
    return {
        "metric": "peak_rss",
        "unit": "bytes",
        "scope": "current_process_lifetime",
        "method": method,
        "peak_rss_bytes": None,
    }


def _process_peak_memory() -> dict[str, object]:
    """Return host-observed peak resident memory for this process when trustworthy.

    Linux and macOS expose ``ru_maxrss`` with different units. Windows exposes
    ``PeakWorkingSetSize`` through ``GetProcessMemoryInfo``. Unsupported or failed
    probes remain explicitly unavailable rather than manufacturing a zero value.
    """

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(ProcessMemoryCounters)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            ok = psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            )
            peak = int(counters.PeakWorkingSetSize) if ok else 0
            if peak > 0:
                return {
                    "metric": "peak_rss",
                    "unit": "bytes",
                    "scope": "current_process_lifetime",
                    "method": "windows_get_process_memory_info",
                    "peak_rss_bytes": peak,
                }
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        return _unavailable_process_memory("windows_get_process_memory_info_unavailable")

    if sys.platform in {"linux", "darwin"}:
        try:
            import resource

            raw_peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            if raw_peak > 0:
                peak = raw_peak if sys.platform == "darwin" else raw_peak * 1024
                return {
                    "metric": "peak_rss",
                    "unit": "bytes",
                    "scope": "current_process_lifetime",
                    "method": (
                        "macos_getrusage" if sys.platform == "darwin" else "linux_getrusage"
                    ),
                    "peak_rss_bytes": peak,
                }
        except (ImportError, OSError, TypeError, ValueError):
            pass
        return _unavailable_process_memory(f"{sys.platform}_getrusage_unavailable")

    return _unavailable_process_memory(f"unsupported_platform:{sys.platform}")


def collect_baseline(repo: Path, task: str = DEFAULT_TASK) -> dict:
    """Collect one descriptive, non-gating Foundation Convergence baseline run.

    The collector intentionally uses Habitat's public workspace lifecycle for the measured
    operations. Timing and process-memory values are observations from one host/run; they
    are not pass/fail thresholds and must not be interpreted as a superiority claim.
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
            process_memory = _process_peak_memory()

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
                "process_memory": process_memory,
                "claim_boundary": (
                    "Descriptive single-run foundation evidence only. Timing, OS-observed process "
                    "peak RSS, and counts vary by host, repository state, installed semantic providers, "
                    "and cache state; process peak RSS covers the current process lifetime and is not "
                    "an allocation attribution for one operation. This report is not a performance "
                    "threshold or a claim of superiority over another agent workflow."
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

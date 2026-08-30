from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from habitat.observability import ObservatoryReadModel


CLAIM_BOUNDARY = (
    "Descriptive Observatory projection/frontend cost evidence only. Measurements are local wall-clock "
    "observations from this run, with no reasoning-quality, task-success, model-capability, or performance-"
    "superiority claim. Unmeasured frontend values are null rather than fabricated zeros."
)


def _compact_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")


def measure_observatory_costs(workspace, *, include_frontend: bool = False) -> dict:
    """Measure explicit, non-persistent Observatory projection/frontend costs.

    The function never records the measurements in Habitat state. Frontend code is imported only
    when the caller explicitly opts in, preserving the headless projection import boundary.
    """

    projection_started = time.perf_counter_ns()
    snapshot = ObservatoryReadModel(workspace).snapshot()
    projection_elapsed_ns = time.perf_counter_ns() - projection_started
    projection_bytes = len(_compact_json_bytes(snapshot))

    frontend_start_ms: float | None = None
    frontend_health_ms: float | None = None

    if include_frontend:
        # Keep transport/browser dependencies outside the headless measurement path.
        from habitat.observatory_frontend import ObservatoryServer

        server = None
        start_started = time.perf_counter_ns()
        try:
            server = ObservatoryServer(workspace).start(open_browser=False)
            frontend_start_ms = (time.perf_counter_ns() - start_started) / 1_000_000

            health_started = time.perf_counter_ns()
            with urllib.request.urlopen(server.url + "api/health", timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status != 200 or not payload.get("ok") or not payload.get("read_only"):
                    raise RuntimeError("Observatory health endpoint did not report a read-only healthy server")
            frontend_health_ms = (time.perf_counter_ns() - health_started) / 1_000_000
        finally:
            if server is not None:
                server.close()

    return {
        "workspace_revision": workspace.revision,
        "headless_projection_wall_ms": projection_elapsed_ns / 1_000_000,
        "headless_projection_bytes": projection_bytes,
        "frontend_start_wall_ms": frontend_start_ms,
        "frontend_health_wall_ms": frontend_health_ms,
        "frontend_included": bool(include_frontend),
        "claim_boundary": CLAIM_BOUNDARY,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="observatory-projection-costs",
        description="Emit descriptive, non-persistent Nolane Habitat Observatory cost evidence.",
    )
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--include-frontend", action="store_true")
    args = parser.parse_args(argv)

    from habitat.workspace import HabitatWorkspace

    with HabitatWorkspace(args.workspace) as workspace:
        report = measure_observatory_costs(workspace, include_frontend=args.include_frontend)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

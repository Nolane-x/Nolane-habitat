from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from tempfile import NamedTemporaryFile
from typing import Callable

from habitat.operations.slo import SloSample


SCHEMA = "foundation-scale-evidence.v1"
GENERATOR = "foundation-scale-fixture.v1"
DEFAULT_TASK = "map deterministic scale fixture"

BaselineCollector = Callable[[Path, str], dict]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _require_non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _fixture_bytes(seed: int, index: int, size: int) -> bytes:
    token = hashlib.sha256(f"{GENERATOR}:{seed}:{index}".encode("utf-8")).hexdigest()
    text = (token * ((size // len(token)) + 1))[:size]
    return text.encode("ascii")


@dataclass(frozen=True)
class ScaleProfile:
    profile_id: str
    repo_files: int
    bytes_per_file: int
    cycles: int
    seed: int
    task: str = DEFAULT_TASK

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _require_non_empty(self.profile_id, "profile_id"))
        object.__setattr__(self, "task", _require_non_empty(self.task, "task"))
        _require_positive_int(self.repo_files, "repo_files")
        _require_positive_int(self.bytes_per_file, "bytes_per_file")
        _require_positive_int(self.cycles, "cycles")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def fixture_manifest(self) -> tuple[dict[str, object], ...]:
        manifest: list[dict[str, object]] = []
        for index in range(self.repo_files):
            content = _fixture_bytes(self.seed, index, self.bytes_per_file)
            manifest.append(
                {
                    "path": f"fixture/file_{index:06d}.txt",
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        return tuple(manifest)

    @property
    def workload_fingerprint(self) -> str:
        payload = {
            "generator": GENERATOR,
            "profile": self.as_dict(),
            "fixture_manifest": list(self.fixture_manifest()),
            "operation_sequence": ["cold_ingest", "warm_reconcile", "orientation"],
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScaleObservation:
    scenario_id: str
    cycle: int
    completed: bool
    latency_ms: float | None
    peak_memory_bytes: int | None
    cold_ingest_ms: float | None
    warm_reconcile_ms: float | None
    orientation_ms: float | None
    memory_measurement_method: str | None = None
    memory_measurement_scope: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScaleEvidence:
    source_commit: str
    profile: ScaleProfile
    workload_fingerprint: str
    observations: tuple[ScaleObservation, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.source_commit, "source_commit")
        if self.workload_fingerprint != self.profile.workload_fingerprint:
            raise ValueError("workload_fingerprint does not match profile")
        if len(self.observations) != self.profile.cycles:
            raise ValueError("observations must match profile cycles")

    def _payload_dict(self) -> dict[str, object]:
        memory_available = any(
            item.peak_memory_bytes is not None for item in self.observations
        )
        return {
            "schema": SCHEMA,
            "source_commit": self.source_commit,
            "profile": self.profile.as_dict(),
            "workload_fingerprint": self.workload_fingerprint,
            "observations": [item.as_dict() for item in self.observations],
            "memory_measurement": (
                "collector_reported_peak_rss" if memory_available else "unavailable"
            ),
            "claim_boundary": (
                "Descriptive deterministic-workload measurements only. Peak memory is accepted only "
                "from an explicit collector-reported peak-RSS record in bytes; the default collector "
                "runs each cycle in a fresh child process so process-lifetime peaks do not leak across "
                "cycles. Missing or unsupported memory remains null. This evidence is not an SLO pass "
                "or a performance superiority claim until joined with an independent matching baseline "
                "and evaluated by an explicit SLO profile."
            ),
        }

    @property
    def evidence_id(self) -> str:
        return hashlib.sha256(
            _canonical_json(self._payload_dict()).encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        value = self._payload_dict()
        value["evidence_id"] = self.evidence_id
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


def _write_fixture(root: Path, profile: ScaleProfile) -> None:
    for index, item in enumerate(profile.fixture_manifest()):
        path = root / str(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _fixture_bytes(profile.seed, index, profile.bytes_per_file)
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise RuntimeError("fixture manifest/content mismatch")
        path.write_bytes(content)


def _default_collector(repo: Path, task: str) -> dict:
    """Run the canonical baseline collector in a fresh process for one scale cycle."""

    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="habitat-scale-baseline-child-") as td:
        out = Path(td) / "baseline.json"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.foundation_baseline",
                "--repo",
                str(repo),
                "--task",
                task,
                "--out",
                str(out),
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "no child output").strip()
            if len(detail) > 2000:
                detail = detail[-2000:]
            raise RuntimeError(
                f"foundation baseline child exited {completed.returncode}: {detail}"
            )
        if not out.is_file():
            raise RuntimeError("foundation baseline child did not create evidence output")
        value = json.loads(out.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("foundation baseline child output must be a JSON object")
        return value


def _wall_ms(report: dict, section: str) -> float:
    value = report.get(section)
    if not isinstance(value, dict):
        raise ValueError(f"collector report missing {section}")
    wall_ms = value.get("wall_ms")
    if isinstance(wall_ms, bool) or not isinstance(wall_ms, (int, float)):
        raise ValueError(f"collector report missing numeric {section}.wall_ms")
    if float(wall_ms) < 0:
        raise ValueError(f"collector report has negative {section}.wall_ms")
    return float(wall_ms)


def _process_memory(report: dict) -> tuple[int | None, str | None, str | None]:
    value = report.get("process_memory")
    if value is None:
        return None, None, None
    if not isinstance(value, dict):
        raise ValueError("collector report process_memory must be an object")
    if value.get("metric") != "peak_rss":
        raise ValueError("collector report process_memory.metric must be peak_rss")
    if value.get("unit") != "bytes":
        raise ValueError("collector report process_memory.unit must be bytes")

    scope = _require_non_empty(value.get("scope"), "process_memory.scope")
    method = _require_non_empty(value.get("method"), "process_memory.method")
    peak = value.get("peak_rss_bytes")
    if peak is None:
        return None, method, scope
    if type(peak) is not int or peak < 1:
        raise ValueError("collector report process_memory.peak_rss_bytes must be positive or null")
    return peak, method, scope


def collect_scale_evidence(
    profile: ScaleProfile,
    *,
    source_commit: str,
    collector: BaselineCollector | None = None,
) -> ScaleEvidence:
    """Measure a deterministic fixture over repeated fresh Habitat baseline lifecycles.

    The default path executes ``benchmarks.foundation_baseline`` in a fresh child process
    for every cycle. That preserves one canonical lifecycle benchmark while making the
    child-reported process-lifetime peak RSS cycle-local. Injected collectors remain
    supported for deterministic tests and may omit memory, which stays explicitly null.
    """

    _require_non_empty(source_commit, "source_commit")
    active_collector = collector or _default_collector
    observations: list[ScaleObservation] = []

    with tempfile.TemporaryDirectory(prefix="habitat-foundation-scale-") as td:
        repo = Path(td) / "fixture-repo"
        repo.mkdir(parents=True, exist_ok=True)
        _write_fixture(repo, profile)

        for cycle in range(1, profile.cycles + 1):
            scenario_id = f"{profile.profile_id}:{cycle:04d}"
            try:
                report = active_collector(repo, profile.task)
                cold_ms = _wall_ms(report, "cold_ingest")
                warm_ms = _wall_ms(report, "warm_reconcile")
                orientation_ms = _wall_ms(report, "orientation")
                peak_memory_bytes, memory_method, memory_scope = _process_memory(report)
                observations.append(
                    ScaleObservation(
                        scenario_id=scenario_id,
                        cycle=cycle,
                        completed=True,
                        latency_ms=cold_ms + warm_ms + orientation_ms,
                        peak_memory_bytes=peak_memory_bytes,
                        cold_ingest_ms=cold_ms,
                        warm_reconcile_ms=warm_ms,
                        orientation_ms=orientation_ms,
                        memory_measurement_method=memory_method,
                        memory_measurement_scope=memory_scope,
                    )
                )
            except Exception as exc:  # evidence preserves failure instead of dropping a cycle
                observations.append(
                    ScaleObservation(
                        scenario_id=scenario_id,
                        cycle=cycle,
                        completed=False,
                        latency_ms=None,
                        peak_memory_bytes=None,
                        cold_ingest_ms=None,
                        warm_reconcile_ms=None,
                        orientation_ms=None,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

    return ScaleEvidence(
        source_commit=source_commit,
        profile=profile,
        workload_fingerprint=profile.workload_fingerprint,
        observations=tuple(observations),
    )


def to_slo_samples(
    current: ScaleEvidence,
    baseline: ScaleEvidence | None,
) -> tuple[SloSample, ...]:
    """Join two independently collected matching evidence artifacts for SLO evaluation."""

    if baseline is None:
        raise ValueError("baseline evidence is required")
    if current.evidence_id == baseline.evidence_id:
        raise ValueError("current and baseline evidence must be independent")
    if current.workload_fingerprint != baseline.workload_fingerprint:
        raise ValueError("current and baseline workload fingerprints must match")

    current_by_id = {item.scenario_id: item for item in current.observations}
    baseline_by_id = {item.scenario_id: item for item in baseline.observations}
    if tuple(current_by_id) != tuple(baseline_by_id):
        raise ValueError("current and baseline scenario identities must match")

    samples: list[SloSample] = []
    for scenario_id, observation in current_by_id.items():
        reference = baseline_by_id[scenario_id]
        samples.append(
            SloSample(
                scenario_id=scenario_id,
                completed=observation.completed,
                latency_ms=observation.latency_ms,
                peak_memory_bytes=observation.peak_memory_bytes,
                baseline_latency_ms=reference.latency_ms,
                baseline_peak_memory_bytes=reference.peak_memory_bytes,
                error=observation.error,
            )
        )
    return tuple(samples)


def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--profile-id", default="foundation-scale-local-v1")
    parser.add_argument("--repo-files", type=int, default=64)
    parser.add_argument("--bytes-per-file", type=int, default=512)
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    profile = ScaleProfile(
        profile_id=args.profile_id,
        repo_files=args.repo_files,
        bytes_per_file=args.bytes_per_file,
        cycles=args.cycles,
        seed=args.seed,
        task=args.task,
    )
    evidence = collect_scale_evidence(profile, source_commit=args.source_commit)
    if args.out:
        _write_json_atomic(args.out, evidence.as_dict())
    print(json.dumps(evidence.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

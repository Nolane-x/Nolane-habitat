"""Run deterministic reliability checks and emit commit-bound evidence.

Fault-injection evidence is always produced. Operational SLO evidence is
optional and is emitted only when an external profile plus measured samples
are explicitly supplied; the runner never invents performance measurements.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
import unittest
from typing import Any, Mapping, Sequence


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from habitat.operations.slo import SloProfile, SloSample, evaluate_slos


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FAULT_TESTS = {
    "tests.test_fault_injection.FaultInjectionTests.test_fault_after_begin_rolls_back_without_leaving_a_transaction_open": "storage.atomic.after_begin",
    "tests.test_fault_injection.FaultInjectionTests.test_fault_before_commit_rolls_back_uncommitted_state": "storage.atomic.before_commit",
    "tests.test_fault_injection.FaultInjectionTests.test_shutdown_fault_is_observable_and_does_not_skip_later_services": "semantic.shutdown.before_close",
}


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_source_commit(source_commit: str) -> None:
    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")


def normalize_reliability_report(
    *, source_commit: str, executed_fault_points: Sequence[str], failures: Sequence[str]
) -> dict[str, Any]:
    """Retain only candidate-bound fault-injection facts from an isolated run."""

    _validate_source_commit(source_commit)
    points = sorted({str(point) for point in executed_fault_points})
    if not points:
        raise ValueError("at least one fault point must be executed")
    failed = sorted({str(name) for name in failures})
    report = {
        "schema": 1,
        "suite": "reliability-faults",
        "source_commit": source_commit,
        "executed_fault_points": points,
        "failures": failed,
        "status": "passed" if not failed else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


def normalize_slo_evidence(
    *,
    source_commit: str,
    profile: SloProfile,
    samples: Sequence[SloSample],
) -> dict[str, Any]:
    """Evaluate externally measured SLO samples and bind the result to a commit.

    Missing measurements remain JSON ``null`` via the underlying SLO domain
    objects.  Sample ordering is canonicalized only for evidence serialization;
    evaluation itself is order-independent and duplicate scenario IDs fail
    closed in :func:`evaluate_slos`.
    """

    _validate_source_commit(source_commit)
    observed = tuple(samples)
    evaluation = evaluate_slos(profile, observed)
    ordered_samples = sorted(observed, key=lambda item: item.scenario_id)
    report: dict[str, Any] = {
        "schema": 1,
        "suite": "operational-slo",
        "evidence_type": "report",
        "source_commit": source_commit,
        "profile": asdict(profile),
        "samples": [asdict(sample) for sample in ordered_samples],
        "evaluation": evaluation.as_dict(),
        "status": "passed" if evaluation.admitted else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


class _ReliabilityResult(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.executed_tests: list[str] = []

    def startTest(self, test: unittest.case.TestCase) -> None:
        self.executed_tests.append(test.id())
        super().startTest(test)


def _run_fault_tests() -> tuple[tuple[str, ...], tuple[str, ...]]:
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_fault_injection")
    runner = unittest.TextTestRunner(
        stream=io.StringIO(), verbosity=0, resultclass=_ReliabilityResult
    )
    result = runner.run(suite)
    failures = [test.id() for test, _ in [*result.failures, *result.errors]]
    failures.extend(test.id() for test in result.unexpectedSuccesses)
    failures.extend(test.id() for test, _ in result.skipped)
    observed = set(result.executed_tests)
    expected = set(_FAULT_TESTS)
    failures.extend(
        f"fault-mapping:unmapped:{test_id}" for test_id in sorted(observed - expected)
    )
    failures.extend(
        f"fault-mapping:unexecuted:{test_id}" for test_id in sorted(expected - observed)
    )
    fault_points = tuple(
        sorted(
            {
                _FAULT_TESTS[test_id]
                for test_id in result.executed_tests
                if test_id in _FAULT_TESTS
            }
        )
    )
    return fault_points, tuple(failures)


def _write_json_atomically(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _read_json(path: Path, *, context: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{context}: {exc}") from exc


def _load_slo_profile(path: Path) -> SloProfile:
    value = _read_json(path, context="SLO profile")
    if not isinstance(value, dict):
        raise ValueError("SLO profile must be a JSON object")
    try:
        return SloProfile(**value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SLO profile: {exc}") from exc


def _load_slo_samples(path: Path) -> tuple[SloSample, ...]:
    value = _read_json(path, context="SLO samples")
    if not isinstance(value, list):
        raise ValueError("SLO samples must be a JSON array")
    samples: list[SloSample] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"SLO samples[{index}] must be a JSON object")
        try:
            samples.append(SloSample(**item))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"SLO samples[{index}]: {exc}") from exc
    return tuple(samples)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--slo-profile", type=Path)
    parser.add_argument("--slo-samples", type=Path)
    parser.add_argument("--slo-out", type=Path)
    args = parser.parse_args(argv)

    slo_values = (args.slo_profile, args.slo_samples, args.slo_out)
    if any(value is not None for value in slo_values) and not all(
        value is not None for value in slo_values
    ):
        parser.error("--slo-profile, --slo-samples, and --slo-out must be supplied together")

    try:
        _validate_source_commit(args.source_commit)
        executed_fault_points, failures = _run_fault_tests()
        fault_report = normalize_reliability_report(
            source_commit=args.source_commit,
            executed_fault_points=executed_fault_points,
            failures=failures,
        )
        _write_json_atomically(args.out, fault_report)

        slo_report: dict[str, Any] | None = None
        if args.slo_profile is not None:
            profile = _load_slo_profile(args.slo_profile)
            samples = _load_slo_samples(args.slo_samples)
            slo_report = normalize_slo_evidence(
                source_commit=args.source_commit,
                profile=profile,
                samples=samples,
            )
            _write_json_atomically(args.slo_out, slo_report)
    except ValueError as exc:
        parser.error(str(exc))

    passed = fault_report["status"] == "passed"
    if slo_report is not None:
        passed = passed and slo_report["status"] == "passed"
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

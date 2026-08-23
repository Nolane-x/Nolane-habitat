"""Run deterministic fault-injection checks and emit commit-bound evidence."""

from __future__ import annotations

import argparse
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


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FAULT_POINTS = (
    "semantic.shutdown.before_close",
    "storage.atomic.after_begin",
    "storage.atomic.before_commit",
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_reliability_report(
    *, source_commit: str, executed_fault_points: Sequence[str], failures: Sequence[str]
) -> dict[str, Any]:
    """Retain only candidate-bound fault-injection facts from an isolated run."""

    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
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


class _ReliabilityResult(unittest.TextTestResult):
    pass


def _run_fault_tests() -> list[str]:
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_fault_injection")
    runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, resultclass=_ReliabilityResult)
    result = runner.run(suite)
    failures = [test.id() for test, _ in [*result.failures, *result.errors]]
    failures.extend(test.id() for test in result.unexpectedSuccesses)
    failures.extend(test.id() for test, _ in result.skipped)
    return failures


def _write_json_atomically(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    report = normalize_reliability_report(
        source_commit=args.source_commit,
        executed_fault_points=_FAULT_POINTS,
        failures=_run_fault_tests(),
    )
    _write_json_atomically(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

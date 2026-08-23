"""Run deterministic SQLite recovery checks and emit commit-bound evidence."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from tempfile import NamedTemporaryFile
import unittest
from typing import Any, Mapping


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_TEST_MODULES = (
    "tests.test_storage_contention",
    "tests.test_storage_migrations",
    "tests.test_storage_recovery",
    "tests.test_storage_doctor",
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_db_recovery_report(
    *, source_commit: str, sqlite_version: str, scenarios: Mapping[str, bool]
) -> dict[str, Any]:
    """Retain only candidate-bound recovery facts from an isolated test run."""

    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    normalized_scenarios = {
        str(name): bool(passed) for name, passed in sorted(scenarios.items())
    }
    failures = [name for name, passed in normalized_scenarios.items() if not passed]
    report = {
        "schema": 1,
        "suite": "database-recovery",
        "source_commit": source_commit,
        "sqlite_version": sqlite_version,
        "checks": ["writer-contention", "nested-rollback", "migration-recovery", "integrity-check", "foreign-key-check"],
        "scenarios": normalized_scenarios,
        "failures": failures,
        "status": "passed" if not failures else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


class _RecoveryResult(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.succeeded: list[str] = []

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self.succeeded.append(test.id())


def _run_recovery_tests() -> dict[str, bool]:
    suite = unittest.defaultTestLoader.loadTestsFromNames(list(_TEST_MODULES))
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0, resultclass=_RecoveryResult)
    result = runner.run(suite)
    scenarios = {name: True for name in result.succeeded}
    for test, _ in [*result.failures, *result.errors]:
        scenarios[test.id()] = False
    for test in result.unexpectedSuccesses:
        scenarios[test.id()] = False
    for test, _ in result.skipped:
        scenarios[test.id()] = False
    return scenarios


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

    report = normalize_db_recovery_report(
        source_commit=args.source_commit,
        sqlite_version=sqlite3.sqlite_version,
        scenarios=_run_recovery_tests(),
    )
    _write_json_atomically(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run hostile protocol transport checks and emit commit-bound evidence."""

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
from typing import Any, Mapping
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_TEST_MODULES = ("tests.test_protocol_conformance",)
_FIXTURE = Path("tests/fixtures/protocol/adversarial-v1alpha2.json")


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def normalize_protocol_conformance_report(*, source_commit: str, fixture_bytes: bytes, scenarios: Mapping[str, bool]) -> dict[str, Any]:
    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    checks = {str(name): bool(passed) for name, passed in sorted(scenarios.items())}
    failures = [name for name, passed in checks.items() if not passed]
    report = {
        "schema": 1,
        "suite": "protocol-conformance",
        "source_commit": source_commit,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "executed_cases": len(checks),
        "scenarios": checks,
        "failures": failures,
        "status": "passed" if not failures else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


class _Result(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.succeeded: list[str] = []

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self.succeeded.append(test.id())


def _run() -> dict[str, bool]:
    suite = unittest.defaultTestLoader.loadTestsFromNames(list(_TEST_MODULES))
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, resultclass=_Result).run(suite)
    checks = {name: True for name in result.succeeded}
    for test, _ in [*result.failures, *result.errors]: checks[test.id()] = False
    for test in [*result.unexpectedSuccesses, *(item[0] for item in result.skipped)]: checks[test.id()] = False
    return checks


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n"); temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True); parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    fixture = Path(__file__).resolve().parents[1] / _FIXTURE
    report = normalize_protocol_conformance_report(source_commit=args.source_commit, fixture_bytes=fixture.read_bytes(), scenarios=_run())
    _write(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

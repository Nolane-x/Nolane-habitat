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

from habitat.protocol import PROTOCOL_VERSION
from habitat.server import serve_stdio

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FIXTURE = Path("tests/fixtures/protocol/adversarial-v1alpha2.json")
_TEST_MODULES = ("tests.test_protocol_conformance",)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate corpus key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-standard corpus number: {value}")


def _load_cases(fixture_bytes: bytes) -> list[dict[str, Any]]:
    try:
        corpus = json.loads(
            fixture_bytes.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid protocol corpus: {exc}") from exc
    if not isinstance(corpus, dict):
        raise ValueError("protocol corpus must be an object")
    if corpus.get("schema") != 1 or corpus.get("protocol") != "habitat.agent.v1alpha2":
        raise ValueError("protocol corpus identity is invalid")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("protocol corpus cases must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"protocol corpus case {index} must be an object")
        case_id = case.get("id")
        raw = case.get("raw")
        expected_kind = case.get("expected_kind")
        error_code = case.get("error_code")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"protocol corpus case {index} id must be a non-empty string")
        if case_id in seen:
            raise ValueError("protocol corpus case ids must be unique")
        if not isinstance(raw, str) or not raw or "\n" in raw or "\r" in raw:
            raise ValueError(f"protocol corpus case {case_id} raw must be one non-empty wire line")
        if expected_kind not in {"success", "error"}:
            raise ValueError(f"protocol corpus case {case_id} expected_kind is invalid")
        if expected_kind == "error" and (not isinstance(error_code, str) or not error_code):
            raise ValueError(f"protocol corpus case {case_id} error kind requires error_code")
        if expected_kind == "success" and error_code is not None:
            raise ValueError(f"protocol corpus case {case_id} success kind cannot define error_code")
        seen.add(case_id)
        normalized.append(
            {
                "id": case_id,
                "raw": raw,
                "expected_kind": expected_kind,
                "expected_error_code": error_code,
            }
        )
    return normalized


class _CorpusWorkspace:
    revision = "protocol-conformance-corpus"

    @staticmethod
    def activity_emit(*args: Any, **kwargs: Any) -> None:
        return None

    @staticmethod
    def record_trace_call(*args: Any, **kwargs: Any) -> None:
        return None


def _observe_wire_kind(raw: str) -> tuple[str, str | None]:
    outgoing = io.StringIO()
    try:
        serve_stdio(_CorpusWorkspace(), io.StringIO(raw + "\n"), outgoing)
    except Exception:
        return "transport-error", None
    lines = outgoing.getvalue().splitlines()
    if len(lines) != 1:
        return "invalid-wire", None
    try:
        response = json.loads(
            lines[0], object_pairs_hook=_strict_object, parse_constant=_reject_constant
        )
    except (json.JSONDecodeError, ValueError):
        return "invalid-wire", None
    if (
        not isinstance(response, dict)
        or response.get("protocol") != PROTOCOL_VERSION
        or "id" not in response
        or type(response.get("ok")) is not bool
        or not isinstance(response.get("revision"), str)
    ):
        return "invalid-envelope", None
    if response["ok"]:
        if "result" not in response or "error" in response:
            return "invalid-envelope", None
        return "success", None
    error = response.get("error")
    if (
        "result" in response
        or not isinstance(error, dict)
        or not isinstance(error.get("code"), str)
        or not error["code"]
        or not isinstance(error.get("message"), str)
        or not isinstance(error.get("details"), dict)
    ):
        return "invalid-envelope", None
    return "error", error["code"]


def _replay_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    for case in cases:
        observed_kind, observed_error_code = _observe_wire_kind(case["raw"])
        passed = observed_kind == case["expected_kind"] and (
            observed_kind != "error"
            or observed_error_code == case["expected_error_code"]
        )
        verdicts.append(
            {
                "id": case["id"],
                "expected_kind": case["expected_kind"],
                "observed_kind": observed_kind,
                "expected_error_code": case["expected_error_code"],
                "observed_error_code": observed_error_code,
                "passed": passed,
            }
        )
    return verdicts


def normalize_protocol_conformance_report(
    *,
    source_commit: str,
    fixture_bytes: bytes,
    unittest_scenarios: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    verdicts = _replay_cases(_load_cases(fixture_bytes))
    checks = {verdict["id"]: verdict["passed"] for verdict in verdicts}
    failures = [verdict["id"] for verdict in verdicts if not verdict["passed"]]
    unittest_checks = {
        str(name): bool(passed)
        for name, passed in sorted((unittest_scenarios or {}).items())
    }
    unittest_failures = [
        name for name, passed in unittest_checks.items() if not passed
    ]
    report = {
        "schema": 1,
        "suite": "protocol-conformance",
        "source_commit": source_commit,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "executed_cases": len(verdicts),
        "case_verdicts": verdicts,
        "scenarios": checks,
        "failures": failures,
        "executed_unittests": len(unittest_checks),
        "unittest_scenarios": unittest_checks,
        "unittest_failures": unittest_failures,
        "status": "passed" if not failures and not unittest_failures else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


class _Result(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.succeeded: list[str] = []

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self.succeeded.append(test.id())


def _run_unittest_coverage() -> dict[str, bool]:
    suite = unittest.defaultTestLoader.loadTestsFromNames(list(_TEST_MODULES))
    result = unittest.TextTestRunner(
        stream=io.StringIO(), verbosity=0, resultclass=_Result
    ).run(suite)
    checks = {name: True for name in result.succeeded}
    for test, _ in [*result.failures, *result.errors]:
        checks[test.id()] = False
    for test in [*result.unexpectedSuccesses, *(item[0] for item in result.skipped)]:
        checks[test.id()] = False
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
    report = normalize_protocol_conformance_report(
        source_commit=args.source_commit,
        fixture_bytes=fixture.read_bytes(),
        unittest_scenarios=_run_unittest_coverage(),
    )
    _write(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

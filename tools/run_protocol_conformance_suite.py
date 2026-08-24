"""Run hostile protocol transport checks and emit commit-bound evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from habitat.protocol import ProtocolError, parse_json_request

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FIXTURE = Path("tests/fixtures/protocol/adversarial-v1alpha2.json")


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


def _load_cases(fixture_bytes: bytes) -> list[dict[str, str]]:
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
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"protocol corpus case {index} must be an object")
        case_id = case.get("id")
        raw = case.get("raw")
        error_code = case.get("error_code")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"protocol corpus case {index} id must be a non-empty string")
        if case_id in seen:
            raise ValueError("protocol corpus case ids must be unique")
        if not isinstance(raw, str) or not isinstance(error_code, str) or not error_code:
            raise ValueError(f"protocol corpus case {case_id} must define raw and error_code strings")
        seen.add(case_id)
        normalized.append({"id": case_id, "raw": raw, "error_code": error_code})
    return normalized


def _replay_cases(cases: list[dict[str, str]]) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    for case in cases:
        observed_error_code: str | None = None
        try:
            parse_json_request(case["raw"])
        except ProtocolError as exc:
            observed_error_code = exc.code
        verdicts.append(
            {
                "id": case["id"],
                "expected_error_code": case["error_code"],
                "observed_error_code": observed_error_code,
                "passed": observed_error_code == case["error_code"],
            }
        )
    return verdicts


def normalize_protocol_conformance_report(*, source_commit: str, fixture_bytes: bytes) -> dict[str, Any]:
    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    verdicts = _replay_cases(_load_cases(fixture_bytes))
    checks = {verdict["id"]: verdict["passed"] for verdict in verdicts}
    failures = [verdict["id"] for verdict in verdicts if not verdict["passed"]]
    report = {
        "schema": 1,
        "suite": "protocol-conformance",
        "source_commit": source_commit,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "executed_cases": len(verdicts),
        "case_verdicts": verdicts,
        "scenarios": checks,
        "failures": failures,
        "status": "passed" if not failures else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


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
        source_commit=args.source_commit, fixture_bytes=fixture.read_bytes()
    )
    _write(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

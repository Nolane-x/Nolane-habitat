"""Merge identity, test-matrix, and scanner artifacts into a fail-honest gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


def _canonical_digest(report: Mapping[str, Any]) -> str | None:
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    try:
        payload = json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(payload).hexdigest()


def _validate_bound_artifact(
    name: str,
    artifact: Mapping[str, Any],
    *,
    expected_suite: str,
    expected_schema: int,
    expected_commit: str,
) -> list[str]:
    failed: list[str] = []
    if artifact.get("suite") != expected_suite:
        failed.append(f"{name}:suite")
    if artifact.get("schema") != expected_schema:
        failed.append(f"{name}:schema")
    if artifact.get("status") != "passed":
        failed.append(f"{name}:status")
    if artifact.get("source_commit") != expected_commit:
        failed.append(f"{name}:source-commit-mismatch")
    if artifact.get("report_sha256") != _canonical_digest(artifact):
        failed.append(f"{name}:report-hash-mismatch")
    return failed


def evaluate_quality_gate(
    *,
    identity: Mapping[str, Any],
    matrix: Mapping[str, Any],
    scanners: Mapping[str, Mapping[str, Any]],
    required_scanners: tuple[str, ...] = (),
    expected_commit: str | None = None,
) -> dict[str, Any]:
    failed: list[str] = []
    if identity.get("_quality_gate_load_error") or not identity.get("ok"):
        failed.append("identity:failed")

    statuses = matrix.get("statuses") if isinstance(matrix.get("statuses"), Mapping) else {}
    if matrix.get("_quality_gate_load_error") or not statuses.get("passed"):
        failed.append("matrix:missing-or-empty")
    for status in ("failed", "timeout", "infra-error"):
        if statuses.get(status, 0):
            failed.append(f"matrix:{status}")

    if expected_commit is not None:
        failed.extend(
            _validate_bound_artifact(
                "identity",
                identity,
                expected_suite="release-identity",
                expected_schema=1,
                expected_commit=expected_commit,
            )
        )
        failed.extend(
            _validate_bound_artifact(
                "matrix",
                matrix,
                expected_suite="isolated-regression-matrix",
                expected_schema=2,
                expected_commit=expected_commit,
            )
        )

    for name in sorted(set(required_scanners)):
        scanner = scanners.get(name)
        if scanner is None:
            failed.append(f"scanner:{name}:missing")
            continue
        if scanner.get("_quality_gate_load_error"):
            failed.append(f"scanner:{name}:unreadable")
        if scanner.get("errors"):
            failed.append(f"scanner:{name}:errors")
        if scanner.get("results"):
            failed.append(f"scanner:{name}:findings")
        if expected_commit is not None:
            if scanner.get("scanner") != name:
                failed.append(f"scanner:{name}:identity-mismatch")
            if scanner.get("source_commit") != expected_commit:
                failed.append(f"scanner:{name}:source-commit-mismatch")
            if scanner.get("status") != "passed":
                failed.append(f"scanner:{name}:status")
            if scanner.get("findings") != 0:
                failed.append(f"scanner:{name}:findings")
            if scanner.get("report_sha256") != _canonical_digest(scanner):
                failed.append(f"scanner:{name}:report-hash-mismatch")

    report = {
        "schema": 1,
        "ok": not failed,
        "failed_gates": failed,
        "identity_ok": bool(identity.get("ok")),
        "matrix_statuses": dict(statuses),
        "scanners": sorted(scanners),
        "required_scanners": sorted(set(required_scanners)),
        "expected_commit": expected_commit,
        "claim_boundary": "This gate evaluates only supplied artifacts. Missing or unreadable required evidence is not a pass.",
    }
    if expected_commit is not None:
        report.update(
            {
                "suite": "truth-core",
                "source_commit": expected_commit,
                "status": "passed" if not failed else "failed",
            }
        )
        report["report_sha256"] = _canonical_digest(report)
    return report


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("artifact root must be an object")
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return {"_quality_gate_load_error": f"{type(exc).__name__}: {exc}"}


def _parse_named_paths(values: list[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path or name in parsed:
            raise ValueError("scanner arguments must use unique NAME=PATH values")
        parsed[name] = Path(raw_path)
    return parsed


def _write_json_atomically(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--scanner", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--require-scanner", action="append", default=[])
    parser.add_argument("--expected-commit")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    scanner_paths = _parse_named_paths(args.scanner)
    report = evaluate_quality_gate(
        identity=_load_json(args.identity),
        matrix=_load_json(args.matrix),
        scanners={name: _load_json(path) for name, path in scanner_paths.items()},
        required_scanners=tuple(args.require_scanner),
        expected_commit=args.expected_commit,
    )
    _write_json_atomically(args.out, report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

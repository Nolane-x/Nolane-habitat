"""Merge identity, test-matrix, and scanner artifacts into a fail-honest gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


def evaluate_quality_gate(
    *,
    identity: Mapping[str, Any],
    matrix: Mapping[str, Any],
    scanners: Mapping[str, Mapping[str, Any]],
    required_scanners: tuple[str, ...] = (),
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

    return {
        "schema": 1,
        "ok": not failed,
        "failed_gates": failed,
        "identity_ok": bool(identity.get("ok")),
        "matrix_statuses": dict(statuses),
        "scanners": sorted(scanners),
        "required_scanners": sorted(set(required_scanners)),
        "claim_boundary": "This gate evaluates only supplied artifacts. Missing or unreadable required evidence is not a pass.",
    }


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
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--scanner", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--require-scanner", action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    scanner_paths = _parse_named_paths(args.scanner)
    report = evaluate_quality_gate(
        identity=_load_json(args.identity),
        matrix=_load_json(args.matrix),
        scanners={name: _load_json(path) for name, path in scanner_paths.items()},
        required_scanners=tuple(args.require_scanner),
    )
    _write_json_atomically(args.out, report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

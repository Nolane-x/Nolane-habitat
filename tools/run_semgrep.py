"""Run Semgrep and emit a compact, commit-bound evidence report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_semgrep_report(
    raw: Mapping[str, Any], *, ruleset: str, source_commit: str, target: str
) -> dict[str, Any]:
    """Retain only release-relevant Semgrep facts and bind them to a candidate."""

    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    results = raw.get("results", [])
    errors = raw.get("errors", [])
    findings = len(results) if isinstance(results, list) else 1
    error_count = len(errors) if isinstance(errors, list) else 1
    report = {
        "schema": 1,
        "scanner": "semgrep",
        "ruleset": ruleset,
        "source_commit": source_commit,
        "target": target,
        "findings": findings,
        "errors": error_count,
        "status": "passed" if findings == 0 and error_count == 0 else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


def _write_json_atomically(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _run_semgrep(ruleset: str, target: str) -> dict[str, Any]:
    executable = os.environ.get("HABITAT_SEMGREP_EXECUTABLE", "semgrep")
    try:
        completed = subprocess.run(
            [executable, "scan", "--error", "--config", ruleset, "--json", target],
            capture_output=True,
            check=False,
            encoding="utf-8",
        )
    except OSError as exc:
        return {"results": [], "errors": [f"semgrep execution failed: {type(exc).__name__}"]}
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raw = {"results": [], "errors": ["semgrep did not emit a JSON report"]}
    if not isinstance(raw, dict):
        raw = {"results": [], "errors": ["semgrep report root was not an object"]}
    if completed.returncode not in (0, 1):
        errors = raw.get("errors")
        raw["errors"] = [*errors, f"semgrep exited with {completed.returncode}"] if isinstance(errors, list) else ["semgrep exited unexpectedly"]
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--ruleset", default="p/github-actions")
    parser.add_argument("--target", default=".github")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = normalize_semgrep_report(
        _run_semgrep(args.ruleset, args.target),
        ruleset=args.ruleset,
        source_commit=args.source_commit,
        target=args.target,
    )
    _write_json_atomically(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

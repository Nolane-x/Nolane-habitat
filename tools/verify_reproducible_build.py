"""Compare two candidate package builds and emit commit-bound reproducibility evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_version(version: str) -> str:
    return re.sub(r"-alpha\.(\d+)$", r"a\1", version)


def _expected_artifacts(version: str) -> dict[str, str]:
    package_version = _package_version(version)
    return {
        "wheel": f"nolane_habitat-{package_version}-py3-none-any.whl",
        "sdist": f"nolane_habitat-{package_version}.tar.gz",
    }


def _collect_build(directory: Path, expected: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    artifacts: dict[str, str] = {}
    failures: list[str] = []
    for name, filename in expected.items():
        path = directory / filename
        if not path.is_file():
            failures.append(f"{name}:missing")
            continue
        artifacts[name] = _sha256_file(path)
    return artifacts, failures


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def verify_reproducible_build(
    *, source_commit: str, version: str, first: Path, second: Path
) -> dict[str, Any]:
    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    expected = _expected_artifacts(version)
    first_build, first_failures = _collect_build(first, expected)
    second_build, second_failures = _collect_build(second, expected)
    failures = [f"first:{failure}" for failure in first_failures]
    failures.extend(f"second:{failure}" for failure in second_failures)
    for name in expected:
        if name in first_build and name in second_build and first_build[name] != second_build[name]:
            failures.append(f"{name}:sha256-mismatch")
    report = {
        "schema": 1,
        "suite": "reproducible-build",
        "source_commit": source_commit,
        "version": version,
        "builds": {"first": first_build, "second": second_build},
        "failures": failures,
        "status": "passed" if not failures else "failed",
    }
    return {**report, "report_sha256": _canonical_digest(report)}


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
    parser.add_argument("--version")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    version = args.version or (args.root / "VERSION").read_text(encoding="utf-8").strip()
    report = verify_reproducible_build(
        source_commit=args.source_commit,
        version=version,
        first=args.first,
        second=args.second,
    )
    _write_json_atomically(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

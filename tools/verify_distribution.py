"""Verify release artifacts and emit commit-bound distribution evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any, Callable


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_version(version: str) -> str:
    return re.sub(r"-alpha\.(\d+)$", r"a\1", version)


def _smoke_import(wheel: Path, expected_version: str) -> bool:
    with TemporaryDirectory(prefix="habitat-wheel-smoke-") as temporary:
        target = Path(temporary) / "site-packages"
        installed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                "--target",
                str(target),
                str(wheel),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if installed.returncode != 0:
            return False
        checked = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import sys; sys.path.insert(0, sys.argv[2]); from habitat import __version__; sys.exit(__version__ != sys.argv[1])",
                expected_version,
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return checked.returncode == 0


def verify_distribution(
    *,
    source_commit: str,
    version: str,
    dist: Path,
    smoke_import: Callable[[Path, str], bool] = _smoke_import,
) -> dict[str, Any]:
    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    package_version = _package_version(version)
    expected = {
        "wheel": dist / f"nolane_habitat-{package_version}-py3-none-any.whl",
        "sdist": dist / f"nolane_habitat-{package_version}.tar.gz",
    }
    failures = [f"{name}:missing" for name, path in expected.items() if not path.is_file()]
    wheel = expected["wheel"]
    smoke_passed = False
    if wheel.is_file():
        smoke_passed = smoke_import(wheel, version)
        if not smoke_passed:
            failures.append("wheel:smoke-import")
    artifacts = [
        {"name": name, "filename": path.name, "sha256": _sha256_file(path), "bytes": path.stat().st_size}
        for name, path in expected.items()
        if path.is_file()
    ]
    report = {
        "schema": 1,
        "suite": "distribution-artifacts",
        "source_commit": source_commit,
        "version": version,
        "artifacts": artifacts,
        "wheel_smoke_import": smoke_passed,
        "failures": failures,
        "status": "passed" if not failures else "failed",
    }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report


def _write_json_atomically(path: Path, value: dict[str, Any]) -> None:
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
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    version = args.version or (args.root / "VERSION").read_text(encoding="utf-8").strip()
    report = verify_distribution(
        source_commit=args.source_commit,
        version=version,
        dist=args.dist,
    )
    _write_json_atomically(args.out, report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify release artifacts and emit commit-bound distribution evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any, Callable
import zipfile


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_PARTS = frozenset({".habitat", ".test-artifacts", "__pycache__"})
_FORBIDDEN_SUFFIXES = (".db", ".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3")


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


def _member_reason(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part)
    if not parts or normalized.startswith("/") or ".." in parts or ":" in parts[0]:
        return "unsafe-member"
    lower_parts = tuple(part.lower() for part in parts)
    if any(part in _FORBIDDEN_PARTS for part in lower_parts):
        return "forbidden-member"
    name = lower_parts[-1]
    if name.startswith(".env") or name.endswith(_FORBIDDEN_SUFFIXES):
        return "forbidden-member"
    return None


def _audit_wheel(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    members: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for entry in sorted(archive.infolist(), key=lambda item: item.filename):
                if entry.is_dir():
                    continue
                reason = _member_reason(entry.filename)
                if stat.S_ISLNK(entry.external_attr >> 16):
                    reason = "unsafe-member"
                if reason:
                    failures.append(f"wheel:{reason}:{entry.filename}")
                members.append({"path": entry.filename, "bytes": entry.file_size})
    except (OSError, zipfile.BadZipFile):
        failures.append("wheel:archive-invalid")
    return members, failures


def _audit_sdist(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    members: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        with tarfile.open(path, "r:gz") as archive:
            for entry in sorted(archive.getmembers(), key=lambda item: item.name):
                if entry.isdir():
                    continue
                reason = _member_reason(entry.name)
                if entry.issym() or entry.islnk() or entry.isdev():
                    reason = "unsafe-member"
                if reason:
                    failures.append(f"sdist:{reason}:{entry.name}")
                members.append({"path": entry.name, "bytes": entry.size})
    except (OSError, tarfile.TarError):
        failures.append("sdist:archive-invalid")
    return members, failures


def _audit_members(expected: dict[str, Path]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    members: dict[str, list[dict[str, Any]]] = {}
    failures: list[str] = []
    for name, path in expected.items():
        if not path.is_file():
            continue
        rows, row_failures = _audit_wheel(path) if name == "wheel" else _audit_sdist(path)
        members[name] = rows
        failures.extend(row_failures)
    return members, failures


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
    members, member_failures = _audit_members(expected)
    failures.extend(member_failures)
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
        "package_members": members,
        "member_manifest_sha256": hashlib.sha256(
            json.dumps(members, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
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

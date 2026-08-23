"""Verify that the current release identity is consistent across public surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile


CURRENT_DOCUMENTS = {
    "README.md": lambda version: version,
}
RELEASE_REF = re.compile(r"--ref\s+v(\d+\.\d+\.\d+-alpha\.\d+)")


def package_version(version: str) -> str:
    return re.sub(r"-alpha\.(\d+)$", r"a\1", version)


def _report_digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def check_identity(root: Path, *, source_commit: str | None = None) -> dict:
    root = root.resolve()
    errors: list[str] = []
    version_path = root / "VERSION"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else ""
    if not re.fullmatch(r"\d+\.\d+\.\d+-alpha\.\d+", version):
        errors.append("VERSION must contain a prerelease identity like 0.1.0-alpha.19")
    expected_package_version = package_version(version) if version else ""

    required_text = {
        "pyproject.toml": f'version = "{expected_package_version}"',
        "habitat/__init__.py": f'__version__ = "{version}"',
        "CHANGELOG.md": f"## {version}",
    }
    for relative, expected in required_text.items():
        path = root / relative
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        if expected not in content:
            errors.append(f"{relative} does not contain {expected!r}")

    for relative, expected_for in CURRENT_DOCUMENTS.items():
        path = root / relative
        expected = expected_for(version)
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        if expected not in content:
            errors.append(f"{relative} does not contain {expected!r}")

    integration = root / "docs" / "CODEX-INTEGRATION.md"
    if integration.is_file():
        for referenced_version in RELEASE_REF.findall(
            integration.read_text(encoding="utf-8")
        ):
            if referenced_version != version:
                errors.append(
                    "docs/CODEX-INTEGRATION.md references "
                    f"v{referenced_version}, not v{version}"
                )

    report = {
        "ok": not errors,
        "version": version,
        "package_version": expected_package_version,
        "errors": errors,
    }
    if source_commit is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            errors.append("source commit must be a 40-character lowercase SHA")
        report.update(
            {
                "schema": 1,
                "suite": "release-identity",
                "source_commit": source_commit,
                "status": "passed" if not errors else "failed",
                "ok": not errors,
            }
        )
        report["report_sha256"] = _report_digest(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-commit")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = check_identity(args.root, source_commit=args.source_commit)
    text = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=args.out.parent, delete=False
        ) as handle:
            handle.write(text + "\n")
            temporary = Path(handle.name)
        os.replace(temporary, args.out)
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

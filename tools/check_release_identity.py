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
    "README.md": lambda version: f"Nolane Habitat {version}",
    "docs/IMPLEMENTATION-STATUS.md": lambda version: f"Implementation Status — {version}",
    "docs/LIMITATIONS.md": lambda version: f"Habitat {version} Limitations and Claim Boundary",
}
LOCAL_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
RELEASE_REF = re.compile(r"--ref\s+v(\d+\.\d+\.\d+-alpha\.\d+)")
RELEASE_MANIFEST_VERSION = re.compile(
    r"build_release_manifest\.py\s+--version\s+(\d+\.\d+\.\d+-alpha\.\d+)"
)


def package_version(version: str) -> str:
    return re.sub(r"-alpha\.(\d+)$", r"a\1", version)


def _report_digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _broken_local_markdown_links(root: Path, relative: str, content: str) -> list[str]:
    base = (root / relative).parent
    broken: list[str] = []
    for raw in LOCAL_MARKDOWN_LINK.findall(content):
        target = raw.split("#", 1)[0].strip()
        if not target:
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        candidate = (base / target).resolve()
        if root != candidate and root not in candidate.parents:
            broken.append(raw)
            continue
        if not candidate.exists():
            broken.append(raw)
    return sorted(set(broken))


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

    plugin_relative = "plugins/nolane-habitat/.codex-plugin/plugin.json"
    plugin_path = root / plugin_relative
    try:
        plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{plugin_relative} is unreadable: {type(exc).__name__}")
    else:
        if not isinstance(plugin, dict) or plugin.get("version") != version:
            errors.append(f"{plugin_relative} version does not match VERSION")

    current_documents: dict[str, str] = {}
    broken_links: list[str] = []
    for relative, expected_for in CURRENT_DOCUMENTS.items():
        path = root / relative
        expected = expected_for(version)
        current_documents[relative] = expected
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        if expected not in content:
            errors.append(f"{relative} does not contain {expected!r}")
        for broken in _broken_local_markdown_links(root, relative, content):
            broken_links.append(broken)
            errors.append(f"{relative} has broken local Markdown link {broken!r}")

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

    release_admission = root / "docs" / "runbooks" / "RELEASE-ADMISSION.md"
    if release_admission.is_file():
        for referenced_version in RELEASE_MANIFEST_VERSION.findall(
            release_admission.read_text(encoding="utf-8")
        ):
            if referenced_version != version:
                errors.append(
                    "docs/runbooks/RELEASE-ADMISSION.md references "
                    f"{referenced_version}, not {version}"
                )

    report = {
        "ok": not errors,
        "version": version,
        "package_version": expected_package_version,
        "current_documents": current_documents,
        "broken_links": sorted(set(broken_links)),
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

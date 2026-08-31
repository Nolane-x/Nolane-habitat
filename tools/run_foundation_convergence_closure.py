"""Actively certify Foundation Convergence evidence against one exact checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile
from typing import Callable


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHELL_META = re.compile(r"(?:&&|\|\||;|`|\$\()")
CommandRunner = Callable[..., tuple[int, str, str]]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(value: dict) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _git_checkout_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = completed.stdout.strip().lower()
    if completed.returncode != 0 or not _COMMIT_SHA.fullmatch(commit):
        detail = completed.stderr.strip() or "git rev-parse HEAD did not return a commit"
        raise ValueError(f"unable to resolve checkout commit: {detail}")
    return commit


def _default_command_runner(
    argv: list[str], *, cwd: Path, env: dict[str, str]
) -> tuple[int, str, str]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _validate_command(raw: object, *, criterion_id: int) -> list[str]:
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValueError(f"criterion {criterion_id} verification command must be a non-empty argv list")
    if not all(isinstance(part, str) and part for part in raw):
        raise ValueError(f"criterion {criterion_id} verification argv must contain non-empty strings")
    command = list(raw)
    if command[0] != "python":
        raise ValueError(f"criterion {criterion_id} verification must use the repository Python runtime")
    if _SHELL_META.search(" ".join(command)):
        raise ValueError(f"criterion {criterion_id} verification contains shell metacharacters")
    return command


def _render_command(
    raw: object,
    *,
    criterion_id: int,
    source_commit: str,
    artifact_dir: Path,
) -> tuple[list[str], list[str]]:
    command = _validate_command(raw, criterion_id=criterion_id)
    substitutions = {
        "source_commit": source_commit,
        "artifact_dir": str(artifact_dir),
    }
    try:
        display = [part.format(**substitutions) for part in command]
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"criterion {criterion_id} verification has an unsupported placeholder"
        ) from exc
    execution = [sys.executable if part == "python" and index == 0 else part for index, part in enumerate(display)]
    return display, execution


def _bounded_failure_text(value: str, *, limit: int = 4000) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[-limit:]


def build_certification_report(
    root: Path,
    *,
    source_commit: str,
    manifest_path: Path,
    artifact_dir: Path,
    command_runner: CommandRunner = _default_command_runner,
    checkout_commit: str | None = None,
) -> dict:
    """Run manifest-declared proof commands and return commit-bound closure evidence."""

    root = root.resolve()
    manifest_path = manifest_path.resolve()
    artifact_dir = artifact_dir.resolve()
    if not _COMMIT_SHA.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")
    resolved_checkout = (checkout_commit or _git_checkout_commit(root)).lower()
    if not _COMMIT_SHA.fullmatch(resolved_checkout):
        raise ValueError("checkout commit must be a 40-character lowercase SHA")
    if resolved_checkout != source_commit:
        raise ValueError(
            f"checkout commit {resolved_checkout} does not match source commit {source_commit}"
        )

    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    entries = manifest.get("criteria")
    if not isinstance(entries, list) or [entry.get("id") for entry in entries] != list(range(1, 13)):
        raise ValueError("closure manifest must contain canonical criteria 1 through 12 in order")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["HABITAT_SOURCE_COMMIT"] = source_commit

    criterion_reports: list[dict] = []
    failed_ids: list[int] = []
    for entry in entries:
        criterion_id = int(entry["id"])
        verification = entry.get("verification")
        if not isinstance(verification, list) or not verification:
            raise ValueError(f"criterion {criterion_id} has no active verification commands")

        checks: list[dict] = []
        for raw_command in verification:
            display_argv, execution_argv = _render_command(
                raw_command,
                criterion_id=criterion_id,
                source_commit=source_commit,
                artifact_dir=artifact_dir,
            )
            returncode, stdout, stderr = command_runner(
                execution_argv,
                cwd=root,
                env=environment,
            )
            check = {
                "argv": display_argv,
                "returncode": int(returncode),
                "status": "passed" if returncode == 0 else "failed",
                "stdout_sha256": _sha256_bytes(stdout.encode("utf-8", errors="replace")),
                "stderr_sha256": _sha256_bytes(stderr.encode("utf-8", errors="replace")),
            }
            if returncode != 0:
                check["stdout_tail"] = _bounded_failure_text(stdout)
                check["stderr_tail"] = _bounded_failure_text(stderr)
            checks.append(check)

        status = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
        if status == "failed":
            failed_ids.append(criterion_id)
        criterion_reports.append(
            {
                "id": criterion_id,
                "criterion": entry["criterion"],
                "status": status,
                "checks": checks,
            }
        )

    report = {
        "schema": 1,
        "suite": "foundation-convergence-certification",
        "source_commit": source_commit,
        "checkout_commit": resolved_checkout,
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "criteria_total": len(criterion_reports),
        "criteria_verified": sum(item["status"] == "passed" for item in criterion_reports),
        "failed_criterion_ids": failed_ids,
        "status": "passed" if not failed_ids and len(criterion_reports) == 12 else "failed",
        "criteria": criterion_reports,
        "claim_boundary": manifest.get("claim_boundary", ""),
    }
    report["report_sha256"] = _canonical_digest(report)
    return report


def _write_json_atomically(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    manifest_path = args.manifest or (root / "docs" / "FOUNDATION-CONVERGENCE-CLOSURE.json")
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    out = args.out if args.out.is_absolute() else root / args.out
    artifact_dir = args.artifact_dir or out.parent / "foundation-convergence-closure"
    if not artifact_dir.is_absolute():
        artifact_dir = root / artifact_dir

    try:
        report = build_certification_report(
            root,
            source_commit=args.source_commit,
            manifest_path=manifest_path,
            artifact_dir=artifact_dir,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"foundation convergence certification error: {exc}", file=sys.stderr)
        return 2

    _write_json_atomically(out, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

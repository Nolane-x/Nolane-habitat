"""Evaluate a release candidate without creating a tag or publishing an artifact."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from habitat.release import (
    REQUIRED_REPORTS,
    ReleaseManifest,
    canonical_report_sha256,
    evaluate_promotion,
    load_json_object,
)


def write_json_atomically(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", choices=sorted(REQUIRED_REPORTS), required=True)
    parser.add_argument("--dry-run", action="store_true", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        manifest = ReleaseManifest.from_dict(
            load_json_object(args.manifest.read_bytes(), context="manifest")
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.commit):
        parser.error("manifest:commit:invalid-sha")
    verdict = evaluate_promotion(manifest, target=args.target)
    value = {
        "source_commit": manifest.commit,
        "manifest_sha256": manifest.manifest_sha256,
        "manifest": {
            "version": manifest.version,
            "commit": manifest.commit,
            "reviewers": manifest.reviewers,
        },
        "dry_run": args.dry_run,
        "publication": "not-attempted",
        "required_reports": sorted(REQUIRED_REPORTS[args.target]),
        "verdict": verdict.as_dict(),
    }
    value["report_sha256"] = canonical_report_sha256(value)
    write_json_atomically(args.out, value)
    return 0 if verdict.admitted else 1


if __name__ == "__main__":
    raise SystemExit(main())

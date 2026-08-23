"""Evaluate a release candidate without creating a tag or publishing an artifact."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from habitat.release import REQUIRED_REPORTS, ReleaseManifest, evaluate_promotion


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

    manifest = ReleaseManifest.from_dict(
        json.loads(args.manifest.read_text(encoding="utf-8"))
    )
    verdict = evaluate_promotion(manifest, target=args.target)
    write_json_atomically(
        args.out,
        {
            "manifest": {"version": manifest.version, "commit": manifest.commit},
            "dry_run": args.dry_run,
            "publication": "not-attempted",
            "required_reports": sorted(REQUIRED_REPORTS[args.target]),
            "verdict": verdict.as_dict(),
        },
    )
    return 0 if verdict.admitted else 1


if __name__ == "__main__":
    raise SystemExit(main())

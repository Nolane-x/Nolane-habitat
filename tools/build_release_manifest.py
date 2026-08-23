"""Hash supplied release evidence and artifacts into a promotion manifest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from habitat.release import build_release_manifest


def _named_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            raise ValueError("evidence arguments must use NAME=PATH")
        if name in result:
            raise ValueError(f"duplicate evidence name: {name}")
        result[name] = Path(raw_path)
    return result


def _write_json_atomically(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--report", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--artifact", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--review", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    manifest = build_release_manifest(
        version=args.version,
        commit=args.commit,
        reports=_named_paths(args.report),
        artifacts=_named_paths(args.artifact),
        residual_risks=tuple(args.risk),
        reviewers=_named_paths(args.review),
    )
    _write_json_atomically(args.out, manifest.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Normalize a source-distribution archive without changing its source contents."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
from pathlib import Path
import tarfile
from tempfile import NamedTemporaryFile


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_member(member: tarfile.TarInfo, *, epoch: int) -> tarfile.TarInfo:
    if not (member.isdir() or member.isfile()):
        raise ValueError(f"unsupported member type: {member.name}")
    normalized = tarfile.TarInfo(member.name)
    normalized.type = member.type
    normalized.mode = member.mode
    normalized.mtime = epoch
    normalized.uid = 0
    normalized.gid = 0
    normalized.uname = ""
    normalized.gname = ""
    normalized.size = member.size if member.isfile() else 0
    return normalized


def normalize_sdist(path: Path, *, epoch: int) -> str:
    """Rewrite *path* with stable archive metadata and return its SHA-256."""
    if epoch < 0:
        raise ValueError("epoch must be non-negative")
    if not path.is_file():
        raise ValueError(f"sdist does not exist: {path}")

    with NamedTemporaryFile("wb", dir=path.parent, delete=False) as destination:
        temporary = Path(destination.name)
    try:
        with tarfile.open(path, "r:gz") as source, temporary.open("wb") as destination:
            with gzip.GzipFile(fileobj=destination, mode="wb", filename="", mtime=epoch) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as normalized:
                    seen: set[str] = set()
                    for member in sorted(source.getmembers(), key=lambda item: item.name):
                        if member.name in seen:
                            raise ValueError(f"duplicate member name: {member.name}")
                        seen.add(member.name)
                        target = _normalized_member(member, epoch=epoch)
                        contents = source.extractfile(member) if member.isfile() else None
                        normalized.addfile(target, contents)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return _sha256_file(path)


def _archive_in(directory: Path) -> Path:
    archives = sorted(directory.glob("*.tar.gz"))
    if len(archives) != 1:
        raise ValueError(f"expected exactly one sdist in {directory}")
    return archives[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sdist", type=Path)
    target.add_argument("--dist", type=Path)
    parser.add_argument("--epoch", type=int, default=0)
    args = parser.parse_args(argv)
    sdist = args.sdist or _archive_in(args.dist)
    print(normalize_sdist(sdist, epoch=args.epoch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

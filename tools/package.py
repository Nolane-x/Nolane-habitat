from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", "dist", "build"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def files():
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS or part.endswith(".egg-info") for part in rel.parts):
            continue
        if p.suffix in EXCLUDE_SUFFIXES:
            continue
        if rel.as_posix() == "reports/DELIVERY-MANIFEST.json":
            continue
        yield p


def write_manifest() -> Path:
    entries = []
    for p in files():
        rel = p.relative_to(ROOT).as_posix()
        entries.append({"path": rel, "size": p.stat().st_size, "sha256": sha256(p)})
    root_hash = hashlib.sha256(
        "\n".join(f"{e['path']}\0{e['size']}\0{e['sha256']}" for e in entries).encode()
    ).hexdigest()
    value = {
        "format": "nolane-habitat-delivery-manifest/v1",
        "version": (ROOT / "VERSION").read_text().strip(),
        "file_count_excluding_manifest": len(entries),
        "root_sha256": root_hash,
        "files": entries,
    }
    out = ROOT / "reports" / "DELIVERY-MANIFEST.json"
    out.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    return out


def build_zip(output: Path) -> None:
    write_manifest()
    all_files = list(files()) + [ROOT / "reports" / "DELIVERY-MANIFEST.json"]
    prefix = ROOT.name
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in sorted(all_files):
            rel = Path(prefix) / p.relative_to(ROOT)
            info = zipfile.ZipInfo(rel.as_posix(), date_time=(2026, 8, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, p.read_bytes())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("output", nargs="?", default=str(ROOT.parent / f"{ROOT.name}-complete-delivery.zip"))
    args = ap.parse_args()
    out = Path(args.output).resolve()
    build_zip(out)
    print(out)

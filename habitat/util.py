from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".java", ".html", ".htm", ".css", ".scss", ".json", ".md", ".txt",
    ".toml", ".yaml", ".yml", ".xml", ".properties", ".gradle", ".kts",
}
# Hard exclusions are restricted to control/state directories that are almost never project source.
# Build/dist are intentionally *not* hard-coded: projects may treat them as authoritative input.
HARD_IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".idea", ".habitat",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8", "surrogatepass")
    return f"{prefix}:{hashlib.sha256(raw).hexdigest()[:20]}"


def utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def detect_language(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript",
        ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
        ".java": "java", ".html": "html", ".htm": "html", ".css": "css", ".scss": "css",
        ".json": "json", ".md": "markdown", ".toml": "toml", ".yaml": "yaml",
        ".yml": "yaml", ".xml": "xml", ".gradle": "gradle", ".kts": "kotlin",
    }.get(ext, "text" if ext in TEXT_EXTENSIONS else "binary")


def _load_pathspec(root: Path):
    """Load .gitignore + .habitatignore if pathspec is available.

    .habitatignore uses gitwildmatch semantics and can add workspace-local exclusions. It does not
    override .gitignore negations; the two files are concatenated in order, so later rules win.
    The core remains usable without pathspec, but reports the reduced policy through callers.
    """
    patterns: list[str] = []
    for name in (".gitignore", ".habitatignore"):
        p = root / name
        if p.is_file():
            try:
                patterns.extend(p.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
    if not patterns:
        return None
    try:
        import pathspec
        if hasattr(pathspec, "GitIgnoreSpec"):
            return pathspec.GitIgnoreSpec.from_lines(patterns)
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    except Exception:
        return None


def iter_project_files(root: Path, *, exclude_roots: Iterable[Path] | None = None, respect_ignore: bool = True) -> Iterable[Path]:
    root = root.resolve()
    excluded = []
    for p in (exclude_roots or []):
        try:
            excluded.append(Path(p).resolve())
        except OSError:
            continue
    spec = _load_pathspec(root) if respect_ignore else None
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        # Never traverse VCS/cache control dirs or explicitly excluded roots. We deliberately do not
        # prune gitignored dirs because a later !negation may re-include descendants.
        kept = []
        for d in dirnames:
            candidate = (base / d).resolve()
            if d in HARD_IGNORE_DIRS:
                continue
            if any(candidate == ex or ex in candidate.parents for ex in excluded):
                continue
            kept.append(d)
        dirnames[:] = kept
        for name in filenames:
            p = base / name
            try:
                if p.is_symlink():
                    continue
                resolved = p.resolve()
            except OSError:
                continue
            if any(resolved == ex or ex in resolved.parents for ex in excluded):
                continue
            rel = p.relative_to(root).as_posix()
            if spec is not None and spec.match_file(rel):
                continue
            yield p


def read_text_lossy(path: Path, max_bytes: int = 2_000_000) -> str:
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def root_digest(entries: list[tuple[str, str]]) -> str:
    payload = json.dumps(sorted(entries), ensure_ascii=False, separators=(",", ":")).encode()
    return sha256_bytes(payload)

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .util import iter_project_files


_WINDOWS_REPLACE_RETRY_DELAYS = (0.005, 0.01, 0.02, 0.04, 0.08)


def _replace_with_retry(tmp: Path, path: Path) -> None:
    """Replace a destination after brief Windows sharing violations."""
    for delay in (*_WINDOWS_REPLACE_RETRY_DELAYS, None):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or delay is None:
                raise
            time.sleep(delay)


class ImportErrorUnsafe(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveLimits:
    max_files: int = 100_000
    max_total_uncompressed: int = 4 * 1024 * 1024 * 1024
    max_file_uncompressed: int = 1024 * 1024 * 1024
    max_compression_ratio: float = 1000.0


def safe_extract_zip(zip_path: Path, destination: Path, limits: ArchiveLimits | None = None) -> None:
    limits = limits or ArchiveLimits()
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > limits.max_files:
            raise ImportErrorUnsafe(f"archive contains too many entries: {len(infos)}")
        total = 0
        for info in infos:
            name = info.filename.replace("\\", "/")
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise ImportErrorUnsafe(f"unsafe archive path: {info.filename}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ImportErrorUnsafe(f"archive symlink rejected: {info.filename}")
            if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                # Some ZIP writers put permission bits without a file type; allow those.
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ImportErrorUnsafe(f"archive special file rejected: {info.filename}")
            if info.flag_bits & 0x1:
                raise ImportErrorUnsafe(f"encrypted archive entry rejected: {info.filename}")
            if info.file_size > limits.max_file_uncompressed:
                raise ImportErrorUnsafe(f"archive entry exceeds uncompressed limit: {info.filename}")
            total += info.file_size
            if total > limits.max_total_uncompressed:
                raise ImportErrorUnsafe("archive exceeds total uncompressed size limit")
            if info.file_size >= 10 * 1024 * 1024:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > limits.max_compression_ratio:
                    raise ImportErrorUnsafe(f"suspicious compression ratio for {info.filename}: {ratio:.1f}")
            target = (destination / Path(*pure.parts)).resolve()
            if target != root and root not in target.parents:
                raise ImportErrorUnsafe(f"archive path escapes destination: {info.filename}")
        zf.extractall(destination)


def prepare_source(source: Path, habitat_dir: Path) -> tuple[Path, str]:
    source = source.expanduser().resolve()
    if source.is_dir():
        return source, "linked-folder"
    if source.is_file() and source.suffix.lower() == ".zip":
        managed = habitat_dir / "managed-source"
        if managed.exists():
            shutil.rmtree(managed)
        safe_extract_zip(source, managed)
        children = [p for p in managed.iterdir() if p.name != ".DS_Store"]
        if len(children) == 1 and children[0].is_dir():
            return children[0], "managed-zip"
        return managed, "managed-zip"
    if source.is_file():
        managed = habitat_dir / "managed-source"
        # A managed-file workspace has exactly one source identity. Reusing a Habitat directory
        # must not silently retain an earlier file alongside the new one.
        if managed.exists():
            shutil.rmtree(managed)
        managed.mkdir(parents=True, exist_ok=True)
        target = managed / source.name
        shutil.copy2(source, target)
        return managed, "managed-file"
    raise FileNotFoundError(source)


def snapshot_metadata(root: Path) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for path in iter_project_files(root):
        try:
            st = path.stat()
        except OSError:
            continue
        out[path.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def atomic_write(path: Path, data: bytes) -> None:
    """Crash-resistant single-file replacement that preserves important file metadata.

    This is atomic at the rename boundary on the local filesystem. Multi-file crash consistency
    is handled by MutationEngine's write-ahead journal/recovery layer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    original_stat = path.stat(follow_symlinks=False) if existed else None
    xattrs: dict[str, bytes] = {}
    if existed and hasattr(os, "listxattr"):
        try:
            for name in os.listxattr(path):
                try:
                    xattrs[name] = os.getxattr(path, name)
                except OSError:
                    pass
        except OSError:
            pass
    # A PID-only temp name collides when two writes to the same path happen concurrently in one
    # process. mkstemp gives each writer a unique file in the destination directory while keeping
    # the final os.replace on the same filesystem.
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.habitat-{os.getpid()}-", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        # Keep the temporary-file descriptor and directory-fsync descriptor as distinct variables.
        # Reusing one integer variable is unsafe under concurrency: after close(), the OS may assign
        # that descriptor number to another thread before a finally block attempts a second close.
        with os.fdopen(tmp_fd, "wb") as f:
            tmp_fd = -1  # fdopen now owns this descriptor exactly once.
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if original_stat is not None:
            os.chmod(tmp, stat.S_IMODE(original_stat.st_mode), follow_symlinks=False)
            if hasattr(os, "chown"):
                try:
                    os.chown(tmp, original_stat.st_uid, original_stat.st_gid, follow_symlinks=False)
                except (PermissionError, OSError):
                    pass
            if hasattr(os, "setxattr"):
                for name, value in xattrs.items():
                    try:
                        os.setxattr(tmp, name, value)
                    except OSError:
                        pass
        _replace_with_retry(tmp, path)
        # fsync the containing directory so the rename itself is durable across a crash.
        if os.name != "nt":
            dir_fd = -1
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
                os.fsync(dir_fd)
            except OSError:
                pass
            finally:
                if dir_fd >= 0:
                    try: os.close(dir_fd)
                    except OSError: pass
                    dir_fd = -1
    finally:
        if tmp_fd >= 0:
            try: os.close(tmp_fd)
            except OSError: pass
            tmp_fd = -1
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass

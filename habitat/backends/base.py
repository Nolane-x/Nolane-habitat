from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..model import ExecutionReceipt


@dataclass(frozen=True)
class SourceStatFingerprint:
    size: int
    mtime_ns: int
    ctime_ns: int
    inode: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceRangeReceipt:
    data: bytes
    authority_bytes_read: int
    start_line: int
    end_line: int
    fingerprint_before: SourceStatFingerprint | None = None
    fingerprint_after: SourceStatFingerprint | None = None


@dataclass(frozen=True)
class SourceAuthorityInfo:
    authority_id: str
    kind: str
    authority: str
    authoritative_root: str
    materialized_root: str
    supports_native_watch: bool = False
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = list(self.capabilities)
        return value


@dataclass(frozen=True)
class ExecutionProviderInfo:
    provider_id: str
    kind: str
    execution_root: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = list(self.capabilities)
        return value


@dataclass(frozen=True)
class BackendInfo:
    """Compatibility view of Habitat's composable substrate.

    Alpha.6 represented source authority and execution placement as one backend. Alpha.7 keeps
    this compatibility record while exposing the two independently bound roles beneath it.
    """

    backend_id: str
    kind: str
    authority: str
    authoritative_root: str
    materialized_root: str
    execution_kind: str
    supports_native_watch: bool = False
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    source_authority_id: str | None = None
    execution_provider_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = list(self.capabilities)
        return value


@dataclass
class BackendSyncReceipt:
    changed_paths: list[str] = field(default_factory=list)
    deleted_paths: list[str] = field(default_factory=list)
    hydrated_paths: list[str] = field(default_factory=list)
    authoritative_bytes_read: int = 0
    authoritative_bytes_written: int = 0
    mode: str = "noop"
    paths_considered: int = 0
    listing_mode: str = "none"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceAuthority(ABC):
    """Owns canonical source bytes and a compiler materialization.

    The materialized root is explicitly derived state. Exact source reads/writes must go through
    this contract so remote/object-store authorities can be introduced without teaching the
    cognitive layer about transport details.
    """

    @property
    @abstractmethod
    def info(self) -> SourceAuthorityInfo:
        raise NotImplementedError

    @property
    @abstractmethod
    def materialized_root(self) -> Path:
        raise NotImplementedError

    @abstractmethod
    def reconcile(self, paths: list[str] | None = None) -> BackendSyncReceipt:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, relpath: str) -> bytes:
        raise NotImplementedError

    def stat_fingerprint(self, relpath: str) -> SourceStatFingerprint | None:
        return None

    def read_line_range(self, relpath: str, start_line: int, end_line: int, *, checkpoint_line: int = 1, checkpoint_offset: int = 0) -> SourceRangeReceipt:
        # Conservative fallback for non-range-capable future authorities. Implementations should override
        # this with range/stream reads so a 200-byte context page does not require downloading a 10MB object.
        raw = self.read_bytes(relpath)
        before = self.stat_fingerprint(relpath)
        lines = raw.splitlines(keepends=True)
        data = b"".join(lines[start_line-1:end_line])
        after = self.stat_fingerprint(relpath)
        return SourceRangeReceipt(data, len(raw), start_line, end_line, before, after)

    @abstractmethod
    def write_bytes(self, relpath: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_file(self, relpath: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, relpath: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def move_file(self, from_relpath: str, to_relpath: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return None


class ExecutionProvider(ABC):
    """Runs typed capabilities against an execution placement.

    Execution is not source authority. A provider may execute against a synchronized checkout,
    container, worker, or future remote computer while source truth remains elsewhere.
    """

    @property
    @abstractmethod
    def info(self) -> ExecutionProviderInfo:
        raise NotImplementedError

    @abstractmethod
    def discover_capabilities(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def run(self, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None) -> ExecutionReceipt:
        raise NotImplementedError

    def close(self) -> None:
        return None


class ProjectBackend(ABC):
    """Compatibility façade over a source authority + execution provider pair."""

    @property
    @abstractmethod
    def info(self) -> BackendInfo:
        raise NotImplementedError

    @property
    @abstractmethod
    def source_authority(self) -> SourceAuthority:
        raise NotImplementedError

    @property
    @abstractmethod
    def execution_provider(self) -> ExecutionProvider:
        raise NotImplementedError

    @property
    def materialized_root(self) -> Path:
        return self.source_authority.materialized_root

    def reconcile(self, paths: list[str] | None = None) -> BackendSyncReceipt:
        return self.source_authority.reconcile(paths)

    def read_bytes(self, relpath: str) -> bytes:
        return self.source_authority.read_bytes(relpath)

    def stat_fingerprint(self, relpath: str) -> SourceStatFingerprint | None:
        return self.source_authority.stat_fingerprint(relpath)

    def read_line_range(self, relpath: str, start_line: int, end_line: int, *, checkpoint_line: int = 1, checkpoint_offset: int = 0) -> SourceRangeReceipt:
        return self.source_authority.read_line_range(relpath, start_line, end_line, checkpoint_line=checkpoint_line, checkpoint_offset=checkpoint_offset)

    def write_bytes(self, relpath: str, data: bytes) -> None:
        self.source_authority.write_bytes(relpath, data)

    def is_file(self, relpath: str) -> bool:
        return self.source_authority.is_file(relpath)

    def delete_file(self, relpath: str) -> None:
        self.source_authority.delete_file(relpath)

    def move_file(self, from_relpath: str, to_relpath: str) -> None:
        self.source_authority.move_file(from_relpath, to_relpath)

    def discover_capabilities(self) -> list[dict]:
        return self.execution_provider.discover_capabilities()

    def run(self, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None) -> ExecutionReceipt:
        return self.execution_provider.run(capability, timeout_s, argv_override)

    def close(self) -> None:
        errors: list[Exception] = []
        for component in (self.execution_provider, self.source_authority):
            try:
                component.close()
            except Exception as exc:  # pragma: no cover - defensive cleanup only
                errors.append(exc)
        if errors:
            raise errors[0]

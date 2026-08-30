from __future__ import annotations

import json
import os
from pathlib import Path

from .base import (
    BackendInfo, BackendSyncReceipt, ExecutionProvider, ExecutionProviderInfo,
    ProjectBackend, SourceAuthority, SourceAuthorityInfo, SourceRangeReceipt, SourceStatFingerprint,
)
from ..execution import (
    containment_probe,
    discover_capabilities,
    resource_limit_probe,
    run_action,
    secret_boundary_probe,
)
from ..sandbox import bubblewrap_probe, run_bwrap_action
from ..security.containment import ContainmentAttestation, ProbeReceipt, unverified_attestation
from ..source_bridge import atomic_write
from ..util import iter_project_files, sha256_bytes, stable_id


def _safe(root: Path, relpath: str) -> Path:
    rel = Path(relpath)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("path escapes backend root")
    root = root.resolve()
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        raise ValueError("path escapes backend root")
    return path


def _fingerprint(path: Path) -> SourceStatFingerprint | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return SourceStatFingerprint(int(st.st_size), int(st.st_mtime_ns), int(getattr(st, "st_ctime_ns", 0)), int(getattr(st, "st_ino", 0)) or None)


def _read_lines(path: Path, start_line: int, end_line: int, checkpoint_line: int, checkpoint_offset: int) -> SourceRangeReceipt:
    if start_line < 1 or end_line < start_line:
        raise ValueError("invalid line range")
    before = _fingerprint(path)
    chunks: list[bytes] = []
    bytes_read = 0
    with path.open("rb") as f:
        if checkpoint_offset > 0:
            f.seek(checkpoint_offset)
        line_no = max(1, int(checkpoint_line))
        while line_no <= end_line:
            line = f.readline()
            if not line:
                break
            bytes_read += len(line)
            if line_no >= start_line:
                chunks.append(line)
            line_no += 1
    after = _fingerprint(path)
    return SourceRangeReceipt(b"".join(chunks), bytes_read, start_line, end_line, before, after)


class LocalSourceAuthority(SourceAuthority):
    def __init__(self, root: Path, *, authority_id: str | None = None, mode: str = "linked-folder"):
        self.root = root.expanduser().resolve()
        self.mode = mode
        self._info = SourceAuthorityInfo(
            authority_id=authority_id or stable_id("authority", "local", str(self.root)),
            kind="local-filesystem",
            authority="source-files",
            authoritative_root=str(self.root),
            materialized_root=str(self.root),
            supports_native_watch=True,
            capabilities=("read", "write", "reconcile", "watch"),
        )

    @property
    def info(self) -> SourceAuthorityInfo:
        return self._info

    @property
    def materialized_root(self) -> Path:
        return self.root

    def reconcile(self, paths: list[str] | None = None) -> BackendSyncReceipt:
        return BackendSyncReceipt(mode="shared-authority", paths_considered=len(paths or []), listing_mode="none")

    def read_bytes(self, relpath: str) -> bytes:
        return _safe(self.root, relpath).read_bytes()

    def stat_fingerprint(self, relpath: str) -> SourceStatFingerprint | None:
        return _fingerprint(_safe(self.root, relpath))

    def read_line_range(self, relpath: str, start_line: int, end_line: int, *, checkpoint_line: int = 1, checkpoint_offset: int = 0) -> SourceRangeReceipt:
        return _read_lines(_safe(self.root, relpath), start_line, end_line, checkpoint_line, checkpoint_offset)

    def write_bytes(self, relpath: str, data: bytes) -> None:
        atomic_write(_safe(self.root, relpath), data)

    def is_file(self, relpath: str) -> bool:
        return _safe(self.root, relpath).is_file()

    def delete_file(self, relpath: str) -> None:
        p = _safe(self.root, relpath)
        if p.is_file():
            p.unlink()

    def move_file(self, from_relpath: str, to_relpath: str) -> None:
        src = _safe(self.root, from_relpath)
        dst = _safe(self.root, to_relpath)
        if not src.is_file():
            raise FileNotFoundError(from_relpath)
        if dst.exists():
            raise FileExistsError(to_relpath)
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)


class DirectoryMirrorSourceAuthority(SourceAuthority):
    """Remote-like authority contract double backed by two directories."""

    def __init__(self, authoritative_root: Path, materialized_root: Path, *, authority_id: str | None = None):
        self.authoritative_root = authoritative_root.expanduser().resolve()
        self._materialized_root = materialized_root.expanduser().resolve()
        self._materialized_root.mkdir(parents=True, exist_ok=True)
        self._info = SourceAuthorityInfo(
            authority_id=authority_id or stable_id("authority", "directory-mirror", str(self.authoritative_root)),
            kind="directory-mirror",
            authority="external-directory",
            authoritative_root=str(self.authoritative_root),
            materialized_root=str(self._materialized_root),
            supports_native_watch=False,
            capabilities=("read", "write", "reconcile", "materialized-mirror"),
        )
        self.reconcile()

    @property
    def info(self) -> SourceAuthorityInfo:
        return self._info

    @property
    def materialized_root(self) -> Path:
        return self._materialized_root

    def _authority_map(self) -> dict[str, Path]:
        return {p.relative_to(self.authoritative_root).as_posix(): p for p in iter_project_files(self.authoritative_root)}

    def _mirror_map(self) -> dict[str, Path]:
        return {p.relative_to(self._materialized_root).as_posix(): p for p in iter_project_files(self._materialized_root)}

    def reconcile(self, paths: list[str] | None = None) -> BackendSyncReceipt:
        changed: list[str] = []
        deleted: list[str] = []
        hydrated: list[str] = []
        bytes_read = 0

        if paths is not None:
            wanted = sorted({Path(rel).as_posix() for rel in paths})
            for rel in wanted:
                ap = _safe(self.authoritative_root, rel)
                mp = _safe(self._materialized_root, rel)
                if not ap.is_file():
                    if mp.is_file():
                        mp.unlink()
                        deleted.append(rel)
                    continue
                a_bytes = ap.read_bytes()
                bytes_read += len(a_bytes)
                mirror_matches = False
                if mp.is_file():
                    mirror_matches = sha256_bytes(mp.read_bytes()) == sha256_bytes(a_bytes)
                if not mirror_matches:
                    atomic_write(mp, a_bytes)
                    changed.append(rel)
                    hydrated.append(rel)
            return BackendSyncReceipt(
                changed_paths=changed, deleted_paths=deleted, hydrated_paths=hydrated,
                authoritative_bytes_read=bytes_read, authoritative_bytes_written=0,
                mode="authority-to-mirror", paths_considered=len(wanted), listing_mode="targeted-no-enumeration",
            )

        auth = self._authority_map()
        mirror = self._mirror_map()
        wanted = set(auth) | set(mirror)
        for rel in sorted(wanted):
            ap = auth.get(rel)
            mp = mirror.get(rel)
            if ap is None:
                if mp is not None and mp.exists():
                    mp.unlink()
                    deleted.append(rel)
                continue
            a_bytes = ap.read_bytes()
            bytes_read += len(a_bytes)
            if mp is None or not mp.exists() or sha256_bytes(mp.read_bytes()) != sha256_bytes(a_bytes):
                atomic_write(_safe(self._materialized_root, rel), a_bytes)
                changed.append(rel)
                hydrated.append(rel)
        for d in sorted((p for p in self._materialized_root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass
        return BackendSyncReceipt(
            changed_paths=changed, deleted_paths=deleted, hydrated_paths=hydrated,
            authoritative_bytes_read=bytes_read, authoritative_bytes_written=0,
            mode="authority-to-mirror", paths_considered=len(wanted), listing_mode="full-enumeration",
        )

    def read_bytes(self, relpath: str) -> bytes:
        return _safe(self.authoritative_root, relpath).read_bytes()

    def stat_fingerprint(self, relpath: str) -> SourceStatFingerprint | None:
        return _fingerprint(_safe(self.authoritative_root, relpath))

    def read_line_range(self, relpath: str, start_line: int, end_line: int, *, checkpoint_line: int = 1, checkpoint_offset: int = 0) -> SourceRangeReceipt:
        return _read_lines(_safe(self.authoritative_root, relpath), start_line, end_line, checkpoint_line, checkpoint_offset)

    def write_bytes(self, relpath: str, data: bytes) -> None:
        atomic_write(_safe(self.authoritative_root, relpath), data)
        atomic_write(_safe(self._materialized_root, relpath), data)

    def is_file(self, relpath: str) -> bool:
        return _safe(self.authoritative_root, relpath).is_file()

    def delete_file(self, relpath: str) -> None:
        ap = _safe(self.authoritative_root, relpath)
        mp = _safe(self._materialized_root, relpath)
        if ap.is_file():
            ap.unlink()
        if mp.is_file():
            mp.unlink()

    def move_file(self, from_relpath: str, to_relpath: str) -> None:
        ap = _safe(self.authoritative_root, from_relpath)
        ad = _safe(self.authoritative_root, to_relpath)
        mp = _safe(self._materialized_root, from_relpath)
        md = _safe(self._materialized_root, to_relpath)
        if not ap.is_file():
            raise FileNotFoundError(from_relpath)
        if ad.exists():
            raise FileExistsError(to_relpath)
        ad.parent.mkdir(parents=True, exist_ok=True)
        os.replace(ap, ad)
        if mp.is_file():
            md.parent.mkdir(parents=True, exist_ok=True)
            if md.exists():
                md.unlink()
            os.replace(mp, md)
        else:
            atomic_write(md, ad.read_bytes())


class LocalExecutionProvider(ExecutionProvider):
    def __init__(self, root: Path, *, provider_id: str | None = None, kind: str = "local-process", containment_profile: str = "trusted-local"):
        self.root = root.expanduser().resolve()
        if containment_profile not in {"trusted-local", "network-contained"}:
            raise ValueError("unsupported containment profile")
        self.containment_profile = containment_profile
        self._info = ExecutionProviderInfo(
            provider_id=provider_id or stable_id("executor", kind, str(self.root)),
            kind=kind,
            execution_root=str(self.root),
            capabilities=("discover", "execute", "network-containment" if containment_profile == "network-contained" else "trusted-local"),
        )

    @property
    def info(self) -> ExecutionProviderInfo:
        return self._info

    def containment_attestation(self) -> ContainmentAttestation:
        if self.containment_profile == "trusted-local":
            return unverified_attestation(
                self.info.provider_id,
                self.info.kind,
                "trusted-local process execution intentionally carries no containment claim",
            )

        namespace = containment_probe()
        limits = resource_limit_probe()
        secrets = secret_boundary_probe()
        network_ok = bool(namespace.get("network_namespace_available"))
        user_ok = bool(namespace.get("user_namespace_available", network_ok))
        namespace_attempted = bool(namespace.get("unshare")) or network_ok or user_ok
        limit_ok = bool(limits.get("available"))
        limit_attempted = bool(limits.get("attempted", bool(limits.get("mechanism")))) or limit_ok
        secret_ok = bool(secrets.get("available"))
        reason = str(namespace.get("reason") or "network/user namespace probe unavailable")
        limit_reason = str(limits.get("reason") or "resource-limit probe unavailable")
        secret_reason = str(secrets.get("reason") or "secret-boundary probe unavailable")
        receipts = (
            ProbeReceipt(
                receipt_id=f"{self.info.provider_id}:probe:network",
                provider_id=self.info.provider_id,
                control="network_isolation",
                mechanism="linux-unshare-user-network",
                attempted=namespace_attempted,
                success=network_ok,
                detail=reason,
            ),
            ProbeReceipt(
                receipt_id=f"{self.info.provider_id}:probe:user",
                provider_id=self.info.provider_id,
                control="user_isolation",
                mechanism="linux-unshare-user-network",
                attempted=namespace_attempted,
                success=user_ok,
                detail=reason,
            ),
            ProbeReceipt(
                receipt_id=f"{self.info.provider_id}:probe:resource",
                provider_id=self.info.provider_id,
                control="resource_limits",
                mechanism=str(limits.get("mechanism") or "posix-rlimit"),
                attempted=limit_attempted,
                success=limit_ok,
                detail=limit_reason,
            ),
            ProbeReceipt(
                receipt_id=f"{self.info.provider_id}:probe:secret",
                provider_id=self.info.provider_id,
                control="secret_boundary",
                mechanism=str(secrets.get("mechanism") or "restricted-environment-allowlist"),
                attempted=True,
                success=secret_ok,
                detail=secret_reason,
            ),
        )
        return ContainmentAttestation(
            provider_id=self.info.provider_id,
            provider_version=self.info.kind,
            process_isolation=False,
            filesystem_isolation=False,
            network_isolation=network_ok,
            user_isolation=user_ok,
            capability_drop=False,
            resource_limits=limit_ok,
            secret_boundary=secret_ok,
            probe_receipts=receipts,
            claim_boundary="network-contained proves only successful user/network namespace, strict POSIX resource-limit, and restricted-environment controls; filesystem and process isolation are not provided",
        )

    def discover_capabilities(self) -> list[dict]:
        return [{**c, "execution_provider_id": self.info.provider_id, "execution_backend": self.info.kind} for c in discover_capabilities(self.root)]

    def run(self, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None):
        receipt = run_action(self.root, capability["id"], list(argv_override or capability["argv"]), timeout_s, capability.get("kind"), self.containment_profile)
        receipt.execution_provider_id = self.info.provider_id
        receipt.execution_backend = self.info.kind
        return receipt


class BubblewrapExecutionProvider(ExecutionProvider):
    """Optional full-sandbox execution provider. Construction is fail-closed when host probing fails."""

    def __init__(self, root: Path, *, provider_id: str | None = None, kind: str = "bubblewrap-sandbox"):
        self.root = root.expanduser().resolve()
        probe = bubblewrap_probe()
        if not probe.get("available"):
            raise RuntimeError("bubblewrap sandbox unavailable: " + str(probe.get("reason")))
        self._probe = probe
        self._info = ExecutionProviderInfo(
            provider_id=provider_id or stable_id("executor", kind, str(self.root)),
            kind=kind,
            execution_root=str(self.root),
            capabilities=("discover", "execute", "full-sandbox", "filesystem-confinement", "network-confinement", "pid-namespace", "secret-env-scrub"),
        )

    @property
    def info(self) -> ExecutionProviderInfo:
        return self._info

    def containment_attestation(self) -> ContainmentAttestation:
        limits = resource_limit_probe()
        limit_ok = bool(limits.get("available"))
        limit_attempted = bool(limits.get("attempted", bool(limits.get("mechanism")))) or limit_ok
        fields = {
            "process_isolation": bool(self._probe.get("pid_namespace")),
            "filesystem_isolation": bool(self._probe.get("filesystem_confinement")),
            "network_isolation": bool(self._probe.get("network_confinement")),
            "user_isolation": bool(self._probe.get("user_namespace")),
            "capability_drop": bool(self._probe.get("capabilities_dropped")),
            "resource_limits": limit_ok,
            "secret_boundary": bool(self._probe.get("secret_environment_scrubbed")),
        }
        probe_reason = str(self._probe.get("reason") or "bubblewrap primitive probe unavailable")
        limit_reason = str(limits.get("reason") or "resource-limit probe unavailable")
        receipts = (
            ProbeReceipt(f"{self.info.provider_id}:probe:process", self.info.provider_id, "process_isolation", "bubblewrap-pid-namespace", True, fields["process_isolation"], probe_reason),
            ProbeReceipt(f"{self.info.provider_id}:probe:filesystem", self.info.provider_id, "filesystem_isolation", "bubblewrap-mount-namespace-bind-profile", True, fields["filesystem_isolation"], probe_reason),
            ProbeReceipt(f"{self.info.provider_id}:probe:network", self.info.provider_id, "network_isolation", "bubblewrap-network-namespace", True, fields["network_isolation"], probe_reason),
            ProbeReceipt(f"{self.info.provider_id}:probe:user", self.info.provider_id, "user_isolation", "bubblewrap-user-namespace", True, fields["user_isolation"], probe_reason),
            ProbeReceipt(f"{self.info.provider_id}:probe:capability", self.info.provider_id, "capability_drop", "bubblewrap-cap-drop-all", True, fields["capability_drop"], probe_reason),
            ProbeReceipt(f"{self.info.provider_id}:probe:resource", self.info.provider_id, "resource_limits", str(limits.get("mechanism") or "posix-rlimit"), limit_attempted, fields["resource_limits"], limit_reason),
            ProbeReceipt(f"{self.info.provider_id}:probe:secret", self.info.provider_id, "secret_boundary", "bubblewrap-clear-environment", True, fields["secret_boundary"], probe_reason),
        )
        return ContainmentAttestation(
            provider_id=self.info.provider_id,
            provider_version=self.info.kind,
            probe_receipts=receipts,
            claim_boundary=str(self._probe.get("claim_boundary") or "Bubblewrap provider evidence does not prove kernel/runtime vulnerabilities and installs no Habitat custom seccomp filter"),
            **fields,
        )

    def discover_capabilities(self) -> list[dict]:
        return [{**c, "execution_provider_id": self.info.provider_id, "execution_backend": self.info.kind, "sandboxed": True} for c in discover_capabilities(self.root)]

    def run(self, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None):
        receipt = run_bwrap_action(self.root, capability, timeout_s, argv_override)
        receipt.execution_provider_id = self.info.provider_id
        receipt.execution_backend = self.info.kind
        return receipt


class CompositeProjectBackend(ProjectBackend):
    def __init__(self, source_authority: SourceAuthority, execution_provider: ExecutionProvider, *, backend_id: str | None = None, kind: str = "composite"):
        self._source_authority = source_authority
        self._execution_provider = execution_provider
        ai = source_authority.info
        ei = execution_provider.info
        self._info = BackendInfo(
            backend_id=backend_id or stable_id("backend", kind, ai.authority_id, ei.provider_id),
            kind=kind,
            authority=ai.authority,
            authoritative_root=ai.authoritative_root,
            materialized_root=ai.materialized_root,
            execution_kind=ei.kind,
            supports_native_watch=ai.supports_native_watch,
            capabilities=tuple(sorted(set(ai.capabilities) | set(ei.capabilities))),
            source_authority_id=ai.authority_id,
            execution_provider_id=ei.provider_id,
        )

    @property
    def info(self) -> BackendInfo:
        return self._info

    @property
    def source_authority(self) -> SourceAuthority:
        return self._source_authority

    @property
    def execution_provider(self) -> ExecutionProvider:
        return self._execution_provider

    def discover_capabilities(self) -> list[dict]:
        out = []
        for c in self.execution_provider.discover_capabilities():
            out.append({**c, "backend_id": self.info.backend_id, "source_authority_id": self.info.source_authority_id})
        return out

    def run(self, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None):
        receipt = self.execution_provider.run(capability, timeout_s, argv_override)
        receipt.backend_id = self.info.backend_id
        receipt.source_authority_id = self.info.source_authority_id
        # A decoupled executor is allowed for observation/test workloads, but source mutations are not
        # silently promoted from an execution checkout into canonical authority. Until a provider exposes
        # an explicit durable write-back contract, fail closed if execution changed project paths.
        exec_root = Path(self.execution_provider.info.execution_root).resolve()
        authority_root = Path(self.source_authority.info.authoritative_root).resolve()
        if receipt.changed_paths and exec_root != authority_root:
            raise RuntimeError("execution mutated a non-authoritative checkout; no durable source write-back bridge is configured")
        return receipt


class LocalProjectBackend(CompositeProjectBackend):
    """Compatibility backend: local authority + local execution on the same root."""

    def __init__(self, root: Path, *, backend_id: str | None = None, mode: str = "linked-folder"):
        authority = LocalSourceAuthority(root, mode=mode)
        executor = LocalExecutionProvider(root, kind="local-process")
        super().__init__(authority, executor, backend_id=backend_id, kind="local-filesystem")
        self.root = authority.root
        self.mode = mode


class DirectoryMirrorBackend(CompositeProjectBackend):
    """Compatibility backend: external-directory authority + execution on authority checkout."""

    def __init__(self, authoritative_root: Path, materialized_root: Path, *, backend_id: str | None = None):
        authority = DirectoryMirrorSourceAuthority(authoritative_root, materialized_root)
        executor = LocalExecutionProvider(authoritative_root, kind="authority-local-process")
        super().__init__(authority, executor, backend_id=backend_id, kind="directory-mirror")
        self.authoritative_root = authority.authoritative_root
        self._materialized_root = authority.materialized_root

    def run(self, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None):
        receipt = super().run(capability, timeout_s, argv_override)
        # Hydrate any authoritative changes into the semantic mirror after execution.
        self.reconcile(receipt.changed_paths or None)
        return receipt


def backend_from_manifest(manifest: dict, habitat_dir: Path) -> ProjectBackend:
    cfg = manifest.get("backend") or {}
    kind = cfg.get("type") or "local-filesystem"
    backend_id = cfg.get("id")

    # Schema 4 can bind authority and execution independently. Older manifests are migrated in memory.
    acfg = manifest.get("source_authority_provider") or {}
    ecfg = manifest.get("execution_provider") or {}
    if acfg or ecfg:
        akind = acfg.get("type") or kind
        authority_id = acfg.get("id")
        if akind == "local-filesystem":
            root = Path(acfg.get("authoritative_root") or cfg.get("authoritative_root") or manifest["source_root"])
            authority: SourceAuthority = LocalSourceAuthority(root, authority_id=authority_id, mode=manifest.get("mode", "linked-folder"))
        elif akind == "directory-mirror":
            authority_root = Path(acfg.get("authoritative_root") or cfg.get("authoritative_root") or manifest["source_root"])
            mirror = Path(acfg.get("materialized_root") or cfg.get("materialized_root") or (habitat_dir / "backend-mirror"))
            authority = DirectoryMirrorSourceAuthority(authority_root, mirror, authority_id=authority_id)
        else:
            raise ValueError(f"unsupported Habitat source authority type: {akind}")

        ekind = ecfg.get("type") or cfg.get("execution_kind") or ("authority-local-process" if akind == "directory-mirror" else "local-process")
        execution_root = Path(ecfg.get("execution_root") or authority.info.authoritative_root)
        if ekind in {"bubblewrap", "bubblewrap-sandbox"} or ecfg.get("containment_profile") == "filesystem-contained":
            executor = BubblewrapExecutionProvider(execution_root, provider_id=ecfg.get("id"), kind="bubblewrap-sandbox")
        else:
            executor = LocalExecutionProvider(execution_root, provider_id=ecfg.get("id"), kind=ekind, containment_profile=ecfg.get("containment_profile", "trusted-local"))
        return CompositeProjectBackend(authority, executor, backend_id=backend_id, kind=kind)

    if kind == "local-filesystem":
        root = Path(cfg.get("authoritative_root") or manifest["source_root"])
        return LocalProjectBackend(root, backend_id=backend_id, mode=manifest.get("mode", "linked-folder"))
    if kind == "directory-mirror":
        authority = Path(cfg.get("authoritative_root") or manifest["source_root"])
        mirror = Path(cfg.get("materialized_root") or (habitat_dir / "backend-mirror"))
        return DirectoryMirrorBackend(authority, mirror, backend_id=backend_id)
    raise ValueError(f"unsupported Habitat backend type: {kind}")

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .admission import SemanticAdmissionRegistry
from .scip_index import ScipIndexSnapshot, parse_scip_index
from .scip_provider import ScipSemanticProvider


DEFAULT_SCIP_INDEXER_TIMEOUT_S = 120.0
SCIP_CAPTURE_RETAIN_BYTES = 64 * 1024
SCIP_TERMINATE_GRACE_S = 2.0


class ScipStaleIndexError(RuntimeError):
    """Raised when an activated SCIP snapshot no longer matches current source truth."""


class ScipGenerationError(RuntimeError):
    """Raised when an explicit SCIP indexer command fails before activation."""

    def __init__(self, status: dict[str, Any]):
        self.status = dict(status)
        message = str(self.status.get("error") or "SCIP index generation failed")
        super().__init__(message)


@dataclass(frozen=True)
class ScipIndexerSpec:
    provider_id: str
    argv: tuple[str, ...]
    output_path: Path
    timeout_s: float = DEFAULT_SCIP_INDEXER_TIMEOUT_S
    env: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("SCIP indexer provider_id must be a non-empty string")
        if not isinstance(self.argv, tuple) or not self.argv:
            raise ValueError("SCIP indexer argv must be a non-empty tuple")
        if any(not isinstance(item, str) or not item or "\x00" in item for item in self.argv):
            raise ValueError("SCIP indexer argv entries must be non-empty NUL-free strings")
        if not isinstance(self.output_path, Path):
            raise TypeError("SCIP indexer output_path must be a pathlib.Path")
        if isinstance(self.timeout_s, bool) or not isinstance(self.timeout_s, (int, float)) or self.timeout_s <= 0:
            raise ValueError("SCIP indexer timeout_s must be a positive number")
        if not isinstance(self.env, tuple):
            raise TypeError("SCIP indexer env must be a tuple of key/value pairs")
        for item in self.env:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("SCIP indexer env entries must be (key, value) tuples")
            key, value = item
            if (
                not isinstance(key, str)
                or not key
                or "=" in key
                or "\x00" in key
                or not isinstance(value, str)
                or "\x00" in value
            ):
                raise ValueError("SCIP indexer env entries must contain valid NUL-free strings")


@dataclass
class _ScipRuntimeState:
    provider: ScipSemanticProvider
    snapshot: ScipIndexSnapshot
    index_path: Path
    activation_revision: str
    source_digests: dict[str, str | None]
    missing_documents: tuple[str, ...]
    document_fingerprint: str
    stale_reason: str | None = None


class ScipRuntimeManager:
    """Workspace-scoped owner for explicitly activated read-only SCIP snapshots.

    The manager never discovers indexes on its own. Activation is the only path that parses an
    index, binds it to current source bytes/revision, and crosses the semantic admission gate.
    Once any bound truth drifts, admission is revoked and remains revoked until explicit
    reactivation.
    """

    def __init__(
        self,
        root: Path,
        semantic_registry: SemanticAdmissionRegistry,
        revision_getter: Callable[[], str],
    ) -> None:
        self.root = Path(root).resolve()
        self.semantic_registry = semantic_registry
        self.revision_getter = revision_getter
        self._providers: dict[str, _ScipRuntimeState] = {}

    def activate(self, index_path: Path, provider_id: str | None = None) -> dict[str, Any]:
        resolved_index = Path(index_path).resolve()
        snapshot = parse_scip_index(resolved_index)
        activation_revision = self._current_revision()
        source_digests, missing_documents = self._bind_sources(snapshot)
        normalized_provider_id = self._provider_id(snapshot, provider_id)
        provider = ScipSemanticProvider(
            snapshot,
            provider_id=normalized_provider_id,
            activation_revision=activation_revision,
            source_digests=source_digests,
        )
        document_fingerprint = self._document_fingerprint(source_digests)

        # Validate the entire replacement candidate before revoking an existing runtime. A malformed
        # replacement therefore cannot destroy a previously admitted, still-fresh provider.
        previous = self._providers.get(normalized_provider_id)
        if previous is not None:
            self.semantic_registry.revoke(normalized_provider_id, "explicit SCIP reactivation")

        if self.semantic_registry.is_registered(normalized_provider_id):
            self.semantic_registry.rebind(provider)
        else:
            self.semantic_registry.register(provider)
        probe = self.semantic_registry.probe(normalized_provider_id)
        if not probe.detected:
            raise ValueError(f"SCIP provider probe failed: {normalized_provider_id}: {probe.reason}")

        stale_reason = None
        if missing_documents:
            stale_reason = "missing indexed documents at activation"
        else:
            self.semantic_registry.admit(
                normalized_provider_id,
                evidence=self._admission_evidence(
                    snapshot,
                    provider,
                    activation_revision,
                    document_fingerprint,
                ),
            )

        state = _ScipRuntimeState(
            provider=provider,
            snapshot=snapshot,
            index_path=resolved_index,
            activation_revision=activation_revision,
            source_digests=source_digests,
            missing_documents=tuple(missing_documents),
            document_fingerprint=document_fingerprint,
            stale_reason=stale_reason,
        )
        self._providers[normalized_provider_id] = state
        return self._status_entry(state)

    def generate(self, spec: ScipIndexerSpec) -> dict[str, Any]:
        """Run one explicit shell-free indexer command, validate its output, then activate it."""
        if not isinstance(spec, ScipIndexerSpec):
            raise TypeError("SCIP generation requires ScipIndexerSpec")
        output_path = self._generation_output_path(spec.output_path)
        environment = os.environ.copy()
        for key, value in spec.env:
            environment[key] = value

        status: dict[str, Any] = {
            "provider_id": spec.provider_id,
            "argv": list(spec.argv),
            "cwd": str(self.root),
            "output_path": str(output_path),
            "exit_code": None,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "stdout_total_bytes": 0,
            "stderr_total_bytes": 0,
            "stdout_truncated": False,
            "stderr_truncated": False,
            "error": "",
        }

        try:
            process = subprocess.Popen(
                list(spec.argv),
                cwd=self.root,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
            )
        except OSError as exc:
            status["error"] = f"failed to start SCIP indexer: {exc}"
            raise ScipGenerationError(status) from exc

        stdout = b""
        stderr = b""
        try:
            stdout, stderr = process.communicate(timeout=float(spec.timeout_s))
        except subprocess.TimeoutExpired:
            status["timed_out"] = True
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=SCIP_TERMINATE_GRACE_S)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()

        stdout = stdout or b""
        stderr = stderr or b""
        status["exit_code"] = process.returncode
        self._retain_generation_stream(status, "stdout", stdout)
        self._retain_generation_stream(status, "stderr", stderr)

        if status["timed_out"]:
            status["error"] = f"SCIP indexer timed out after {float(spec.timeout_s):g}s"
            raise ScipGenerationError(status)
        if process.returncode != 0:
            status["error"] = f"SCIP indexer exited with status {process.returncode}"
            raise ScipGenerationError(status)
        if not output_path.is_file():
            status["error"] = "SCIP indexer completed successfully but output file was not produced"
            raise ScipGenerationError(status)

        activated = self.activate(output_path, provider_id=spec.provider_id)
        activated["generation"] = status
        return activated

    def definitions(self, provider_id: str, symbol: str) -> dict[str, Any]:
        state = self._require_fresh(provider_id)
        return state.provider.definitions(symbol)

    def references(self, provider_id: str, symbol: str) -> dict[str, Any]:
        state = self._require_fresh(provider_id)
        return state.provider.references(symbol)

    def document(self, provider_id: str, path: Path) -> dict[str, Any]:
        state = self._require_fresh(provider_id)
        relative = self._workspace_relative(path)
        if state.source_digests.get(relative) is None:
            self._mark_stale(state, f"indexed document is unavailable: {relative}")
            raise ScipStaleIndexError(state.stale_reason or "SCIP index is stale")
        return state.provider.document(relative)

    def status(self) -> dict[str, Any]:
        providers: list[dict[str, Any]] = []
        for provider_id in sorted(self._providers):
            state = self._providers[provider_id]
            self._reconcile_state(state)
            providers.append(self._status_entry(state))
        return {"providers": providers}

    def reconcile_admissions(self) -> None:
        for state in self._providers.values():
            self._reconcile_state(state)

    def close_provider(self, provider_id: str) -> None:
        state = self._providers.pop(provider_id, None)
        if state is None:
            if self.semantic_registry.is_registered(provider_id):
                self.semantic_registry.revoke(provider_id, "SCIP runtime closed")
            return
        self.semantic_registry.revoke(provider_id, "SCIP runtime closed")

    def close(self) -> None:
        for provider_id in tuple(self._providers):
            self.close_provider(provider_id)

    def _require_fresh(self, provider_id: str) -> _ScipRuntimeState:
        state = self._providers.get(provider_id)
        if state is None:
            raise KeyError(provider_id)
        self._reconcile_state(state)
        if state.stale_reason is not None or not self.semantic_registry.is_admitted(provider_id):
            reason = state.stale_reason or "SCIP provider is not admitted"
            raise ScipStaleIndexError(f"{provider_id}: {reason}; explicit reactivation required")
        return state

    def _reconcile_state(self, state: _ScipRuntimeState) -> None:
        if state.stale_reason is not None:
            if self.semantic_registry.is_admitted(state.provider.id):
                self.semantic_registry.revoke(state.provider.id, state.stale_reason)
            return

        current_revision = self._current_revision()
        if current_revision != state.activation_revision:
            self._mark_stale(
                state,
                f"Habitat revision changed: {state.activation_revision} -> {current_revision}",
            )
            return

        for relative_path, expected_digest in state.source_digests.items():
            if expected_digest is None:
                self._mark_stale(state, f"indexed document is unavailable: {relative_path}")
                return
            materialized = self._materialize_document(relative_path)
            if not materialized.is_file():
                self._mark_stale(state, f"indexed document disappeared: {relative_path}")
                return
            current_digest = self._sha256_file(materialized)
            if current_digest != expected_digest:
                self._mark_stale(state, f"source digest changed: {relative_path}")
                return

    def _mark_stale(self, state: _ScipRuntimeState, reason: str) -> None:
        if state.stale_reason is None:
            state.stale_reason = reason
        if self.semantic_registry.is_admitted(state.provider.id):
            self.semantic_registry.revoke(state.provider.id, state.stale_reason)

    def _bind_sources(self, snapshot: ScipIndexSnapshot) -> tuple[dict[str, str | None], list[str]]:
        source_digests: dict[str, str | None] = {}
        missing: list[str] = []
        for document in snapshot.documents:
            materialized = self._materialize_document(document.path)
            if not materialized.is_file():
                source_digests[document.path] = None
                missing.append(document.path)
                continue
            source_digests[document.path] = self._sha256_file(materialized)
        return source_digests, sorted(missing)

    def _materialize_document(self, relative_path: str) -> Path:
        # scip_index already requires canonical POSIX relative paths. Re-check containment here at
        # the source-authority boundary so future parser changes cannot accidentally weaken it.
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError(f"invalid SCIP document path: {relative_path!r}")
        candidate = self.root.joinpath(*pure.parts).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"SCIP document escapes source root: {relative_path!r}") from exc
        return candidate

    def _workspace_relative(self, path: Path) -> str:
        raw = Path(path)
        candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"SCIP query path escapes source root: {path}") from exc
        value = relative.as_posix()
        if not value or value == ".":
            raise ValueError("SCIP document query requires a file below the source root")
        return value

    def _generation_output_path(self, path: Path) -> Path:
        raw = Path(path)
        candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"SCIP generation output escapes workspace root: {path}") from exc
        if candidate.suffix != ".scip":
            raise ValueError("SCIP generation output must be a .scip artifact")
        return candidate

    def _provider_id(self, snapshot: ScipIndexSnapshot, provider_id: str | None) -> str:
        if provider_id is None:
            tool = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in snapshot.tool.name)
            tool = tool.strip("-") or "index"
            return f"scip.{tool}.{snapshot.index_digest[:12]}"
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("SCIP provider_id must be a non-empty string")
        return provider_id.strip()

    def _current_revision(self) -> str:
        value = self.revision_getter()
        if not isinstance(value, str) or not value:
            raise ValueError("SCIP runtime requires a non-empty Habitat revision")
        return value

    @staticmethod
    def _retain_generation_stream(status: dict[str, Any], name: str, payload: bytes) -> None:
        total = len(payload)
        retained = payload[-SCIP_CAPTURE_RETAIN_BYTES:]
        status[f"{name}_total_bytes"] = total
        status[f"{name}_truncated"] = total > len(retained)
        status[name] = retained.decode("utf-8", errors="replace")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _document_fingerprint(source_digests: dict[str, str | None]) -> str:
        payload = [
            {"path": path, "sha256": source_digests[path]}
            for path in sorted(source_digests)
        ]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _admission_evidence(
        snapshot: ScipIndexSnapshot,
        provider: ScipSemanticProvider,
        activation_revision: str,
        document_fingerprint: str,
    ) -> tuple[str, ...]:
        return (
            f"scip.index.sha256={snapshot.index_digest}",
            f"scip.tool.name={snapshot.tool.name}",
            f"scip.tool.version={snapshot.tool.version}",
            f"scip.project_root={snapshot.project_root}",
            f"scip.activation_revision={activation_revision}",
            f"scip.documents.sha256={document_fingerprint}",
            f"scip.provider.sha256={provider.provider_fingerprint()}",
        )

    def _status_entry(self, state: _ScipRuntimeState) -> dict[str, Any]:
        provider_id = state.provider.id
        return {
            "provider_id": provider_id,
            "detected": True,
            "admitted": self.semantic_registry.is_admitted(provider_id),
            "stale": state.stale_reason is not None,
            "stale_reason": state.stale_reason,
            "activation_revision": state.activation_revision,
            "current_revision": self._current_revision(),
            "index_path": str(state.index_path),
            "index_digest": state.snapshot.index_digest,
            "provider_fingerprint": state.provider.provider_fingerprint(),
            "project_root": state.snapshot.project_root,
            "tool": {
                "name": state.snapshot.tool.name,
                "version": state.snapshot.tool.version,
                "arguments": list(state.snapshot.tool.arguments),
            },
            "document_fingerprint": state.document_fingerprint,
            "source_digests": dict(state.source_digests),
            "missing_documents": list(state.missing_documents),
            "languages": sorted(state.provider.languages),
            "capabilities": sorted(state.provider.capabilities),
            "source_authority": False,
            "mutation_authority": False,
        }


__all__ = [
    "ScipGenerationError",
    "ScipIndexerSpec",
    "ScipRuntimeManager",
    "ScipStaleIndexError",
]

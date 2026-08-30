from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .containment import ContainmentAttestation


@dataclass(frozen=True)
class ExecutionCapability:
    profile: str
    sandboxed: bool
    network_restricted: bool
    filesystem_restricted: bool
    process_isolated: bool
    verified_by: tuple[str, ...]
    containment_attestation: dict[str, Any] = field(default_factory=dict)
    attestation_fingerprint: str = ""


@dataclass(frozen=True)
class CapabilityReport:
    source_authority: dict[str, Any]
    execution: ExecutionCapability
    mutation: dict[str, Any]
    observatory: dict[str, Any]
    generated_at_revision: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_capability_report(
    *,
    source_authority: Mapping[str, Any],
    execution_provider: Mapping[str, Any],
    generated_at_revision: str,
    execution_attestation: ContainmentAttestation | None = None,
) -> CapabilityReport:
    provider_id = str(execution_provider.get("provider_id") or "")
    if execution_attestation is not None and execution_attestation.provider_id != provider_id:
        raise ValueError("execution containment attestation provider does not match execution provider")

    attestation = execution_attestation
    verified_sandbox = bool(
        attestation is not None
        and attestation.filesystem_isolation
        and attestation.network_isolation
        and attestation.process_isolation
        and attestation.user_isolation
        and attestation.capability_drop
    )
    execution = ExecutionCapability(
        profile="verified-sandbox" if verified_sandbox else "trusted-local-process",
        sandboxed=verified_sandbox,
        network_restricted=bool(attestation and attestation.network_isolation),
        filesystem_restricted=bool(attestation and attestation.filesystem_isolation),
        process_isolated=bool(attestation and attestation.process_isolation),
        verified_by=(provider_id,) if verified_sandbox and provider_id else (),
        containment_attestation=attestation.as_dict() if attestation is not None else {},
        attestation_fingerprint=attestation.fingerprint if attestation is not None else "",
    )
    return CapabilityReport(
        source_authority={
            "authority_id": source_authority.get("authority_id"),
            "kind": source_authority.get("kind"),
            "authority": source_authority.get("authority"),
            "capabilities": list(source_authority.get("capabilities") or ()),
        },
        execution=execution,
        mutation={"governance": "workspace-policy", "journaled": True},
        observatory={"default_bind": "127.0.0.1", "http_read_only": True},
        generated_at_revision=generated_at_revision,
    )


def require_capability(report: CapabilityReport, name: str) -> None:
    values = {
        "sandboxed": report.execution.sandboxed,
        "network_restricted": report.execution.network_restricted,
        "filesystem_restricted": report.execution.filesystem_restricted,
        "process_isolated": report.execution.process_isolated,
    }
    if not values.get(name, False):
        raise PermissionError(f"required capability is not verified: {name}")

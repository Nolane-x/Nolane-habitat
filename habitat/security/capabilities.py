from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionCapability:
    profile: str
    sandboxed: bool
    network_restricted: bool
    filesystem_restricted: bool
    process_isolated: bool
    verified_by: tuple[str, ...]


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
) -> CapabilityReport:
    capabilities = frozenset(execution_provider.get("capabilities") or ())
    verified_sandbox = {
        "full-sandbox",
        "filesystem-confinement",
        "network-confinement",
        "pid-namespace",
    } <= capabilities
    provider_id = str(execution_provider.get("provider_id") or "")
    execution = ExecutionCapability(
        profile="verified-sandbox" if verified_sandbox else "trusted-local-process",
        sandboxed=verified_sandbox,
        network_restricted=verified_sandbox,
        filesystem_restricted=verified_sandbox,
        process_isolated=verified_sandbox,
        verified_by=(provider_id,) if verified_sandbox and provider_id else (),
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

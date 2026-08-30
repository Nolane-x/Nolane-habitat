from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


CONTAINMENT_CONTROLS: tuple[str, ...] = (
    "process_isolation",
    "filesystem_isolation",
    "network_isolation",
    "user_isolation",
    "capability_drop",
    "resource_limits",
    "secret_boundary",
)
_CONTROL_SET = frozenset(CONTAINMENT_CONTROLS)


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")
    return value


@dataclass(frozen=True)
class ProbeReceipt:
    receipt_id: str
    provider_id: str
    control: str
    mechanism: str
    attempted: bool
    success: bool
    detail: str

    def __post_init__(self) -> None:
        _require_text(self.receipt_id, "receipt_id")
        _require_text(self.provider_id, "provider_id")
        _require_text(self.mechanism, "mechanism")
        _require_text(self.detail, "detail")
        if self.control not in _CONTROL_SET:
            raise ValueError(f"unknown containment control: {self.control}")
        _require_bool(self.attempted, "attempted")
        _require_bool(self.success, "success")
        if self.success and not self.attempted:
            raise ValueError("successful containment probe must have attempted=True")

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "provider_id": self.provider_id,
            "control": self.control,
            "mechanism": self.mechanism,
            "attempted": self.attempted,
            "success": self.success,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ContainmentAttestation:
    provider_id: str
    provider_version: str
    process_isolation: bool
    filesystem_isolation: bool
    network_isolation: bool
    user_isolation: bool
    capability_drop: bool
    resource_limits: bool
    secret_boundary: bool
    probe_receipts: tuple[ProbeReceipt, ...]
    claim_boundary: str

    def __post_init__(self) -> None:
        _require_text(self.provider_id, "provider_id")
        _require_text(self.provider_version, "provider_version")
        _require_text(self.claim_boundary, "claim_boundary")

        for control in CONTAINMENT_CONTROLS:
            _require_bool(getattr(self, control), control)

        if isinstance(self.probe_receipts, (str, bytes)):
            raise TypeError("probe_receipts must be an iterable of ProbeReceipt")
        try:
            receipts = tuple(self.probe_receipts)
        except TypeError as exc:
            raise TypeError("probe_receipts must be an iterable of ProbeReceipt") from exc

        receipt_ids: set[str] = set()
        for item in receipts:
            if not isinstance(item, ProbeReceipt):
                raise TypeError("probe_receipts entries must be ProbeReceipt")
            if item.provider_id != self.provider_id:
                raise ValueError("probe receipt provider does not match attestation provider")
            if item.receipt_id in receipt_ids:
                raise ValueError(f"duplicate probe receipt id: {item.receipt_id}")
            receipt_ids.add(item.receipt_id)

        receipts = tuple(sorted(receipts, key=lambda item: (CONTAINMENT_CONTROLS.index(item.control), item.receipt_id)))
        object.__setattr__(self, "probe_receipts", receipts)

        for control in CONTAINMENT_CONTROLS:
            if not getattr(self, control):
                continue
            if not any(item.control == control and item.success for item in receipts):
                raise ValueError(
                    f"containment control {control} requires a successful same-provider probe receipt"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "process_isolation": self.process_isolation,
            "filesystem_isolation": self.filesystem_isolation,
            "network_isolation": self.network_isolation,
            "user_isolation": self.user_isolation,
            "capability_drop": self.capability_drop,
            "resource_limits": self.resource_limits,
            "secret_boundary": self.secret_boundary,
            "probe_receipts": [item.as_dict() for item in self.probe_receipts],
            "claim_boundary": self.claim_boundary,
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.as_dict(),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


def unverified_attestation(
    provider_id: str,
    provider_version: str,
    claim_boundary: str,
) -> ContainmentAttestation:
    return ContainmentAttestation(
        provider_id=provider_id,
        provider_version=provider_version,
        process_isolation=False,
        filesystem_isolation=False,
        network_isolation=False,
        user_isolation=False,
        capability_drop=False,
        resource_limits=False,
        secret_boundary=False,
        probe_receipts=(),
        claim_boundary=claim_boundary,
    )

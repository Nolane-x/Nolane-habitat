from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .util import utc_now


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    action: str
    risk: str
    reason: str
    approval_required: bool = False
    matched_rule: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "risk": self.risk,
            "reason": self.reason,
            "approval_required": self.approval_required,
            "matched_rule": self.matched_rule,
        }


DEFAULT_POLICY = {
    "schema": 1,
    "mode": "trusted-development",
    "source": {
        "read": ["**"],
        "edit": ["**"],
        "approval": [],
        "deny": [".git/**", ".habitat/**"],
    },
    "execution": {
        "allow_kinds": ["test", "build", "script", "service"],
        "approval_kinds": [],
        "deny_capabilities": [],
        "require_sandbox_for_untrusted": True,
    },
    "browser": {"allow_external": False},
    "structural_mutation": {"approval_required": False},
    "updated_at": None,
}


class PolicyEngine:
    """Small, explicit authorization layer for consequential Habitat actions.

    It is deliberately not an enterprise IAM system. The goal is to make policy decisions typed,
    inspectable and enforceable at the mutation/execution boundary instead of encoding them as
    scattered booleans in callers.
    """

    FILE = "policy.json"

    def __init__(self, habitat_dir: Path):
        self.path = habitat_dir / self.FILE
        if not self.path.exists():
            value = json.loads(json.dumps(DEFAULT_POLICY))
            value["updated_at"] = utc_now()
            self.path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        self._value = self._load()

    def _load(self) -> dict:
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema") != 1:
            raise ValueError("unsupported Habitat policy schema")
        if value.get("mode") not in {"trusted-development", "restricted", "untrusted"}:
            raise ValueError("invalid Habitat policy mode")
        return value

    def status(self) -> dict:
        self._value = self._load()
        return json.loads(json.dumps(self._value))

    def update(self, patch: dict) -> dict:
        if not isinstance(patch, dict):
            raise TypeError("policy patch must be an object")
        current = self.status()
        allowed_top = {"mode", "source", "execution", "browser", "structural_mutation"}
        unknown = set(patch) - allowed_top
        if unknown:
            raise ValueError(f"unknown policy fields: {sorted(unknown)}")
        for key, value in patch.items():
            if key == "mode":
                if value not in {"trusted-development", "restricted", "untrusted"}:
                    raise ValueError("invalid policy mode")
                current[key] = value
            else:
                if not isinstance(value, dict):
                    raise TypeError(f"policy {key} must be an object")
                current.setdefault(key, {}).update(value)
        current["schema"] = 1
        current["updated_at"] = utc_now()
        self.path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
        self._value = self._load()
        return self.status()

    @staticmethod
    def _matches(path: str, patterns: list[str]) -> bool:
        p = path.replace("\\", "/")
        return any(fnmatch.fnmatch(p, pattern) or (pattern == "**") for pattern in patterns)

    def evaluate_source(self, action: str, path: str, *, structural: bool = False) -> PolicyDecision:
        value = self.status(); source = value.get("source") or {}
        deny = list(source.get("deny") or [])
        if self._matches(path, deny):
            return PolicyDecision(False, action, "high", f"source path denied by policy: {path}", matched_rule="source.deny")
        allow_key = "read" if action == "read" else "edit"
        allow = list(source.get(allow_key) or [])
        if not self._matches(path, allow):
            return PolicyDecision(False, action, "medium", f"source path not allowed for {action}: {path}", matched_rule=f"source.{allow_key}")
        path_approval = action != "read" and self._matches(path,list(source.get("approval") or []))
        structural_approval = bool(structural and (value.get("structural_mutation") or {}).get("approval_required", False))
        approval = path_approval or structural_approval
        matched = "source.approval" if path_approval else "structural_mutation.approval_required" if structural_approval else f"source.{allow_key}"
        reason = "source action allowed" if not approval else ("path requires approval" if path_approval else "structural mutation requires approval")
        return PolicyDecision(not approval, action, "high" if path_approval else "medium" if structural else "low", reason, approval, matched)

    def evaluate_execution(self, capability: dict, *, sandboxed: bool) -> PolicyDecision:
        value = self.status(); ex = value.get("execution") or {}; mode=value.get("mode")
        cid=str(capability.get("id") or ""); kind=str(capability.get("kind") or "script")
        if cid in set(ex.get("deny_capabilities") or []):
            return PolicyDecision(False, "execute", "high", f"capability denied: {cid}", matched_rule="execution.deny_capabilities")
        if kind not in set(ex.get("allow_kinds") or []):
            return PolicyDecision(False, "execute", "high", f"capability kind not allowed: {kind}", matched_rule="execution.allow_kinds")
        if mode == "untrusted" and bool(ex.get("require_sandbox_for_untrusted", True)) and not sandboxed:
            return PolicyDecision(False, "execute", "critical", "untrusted policy requires a sandboxed execution provider", matched_rule="execution.require_sandbox_for_untrusted")
        approval = kind in set(ex.get("approval_kinds") or [])
        return PolicyDecision(not approval, "execute", "high" if kind=="service" else "medium", "execution allowed" if not approval else "execution requires approval", approval, "execution.allow_kinds")

    def evaluate_browser_external(self) -> PolicyDecision:
        allowed=bool((self.status().get("browser") or {}).get("allow_external",False))
        return PolicyDecision(allowed,"browser.external","high","external browser access allowed" if allowed else "external browser access denied by policy",False,"browser.allow_external")

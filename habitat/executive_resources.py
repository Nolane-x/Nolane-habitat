from __future__ import annotations

import time
from typing import Any

from .executive import EXECUTIVE_PHASES
from .util import utc_now


BUDGET_LIMIT_MINIMUMS: dict[str, int] = {
    "max_steps": 1,
    "max_failed_steps": 0,
    "max_strategy_switches": 0,
    "max_wall_time_ms": 0,
    "max_tool_calls": 0,
    "max_input_tokens": 0,
    "max_output_tokens": 0,
    "max_compute_ms": 0,
}

PROVIDER_LIMITS: dict[str, tuple[str, str]] = {
    "max_tool_calls": ("tool_calls", "TOOL_CALL_BUDGET_EXHAUSTED"),
    "max_input_tokens": ("input_tokens", "INPUT_TOKEN_BUDGET_EXHAUSTED"),
    "max_output_tokens": ("output_tokens", "OUTPUT_TOKEN_BUDGET_EXHAUSTED"),
    "max_compute_ms": ("compute_ms", "COMPUTE_BUDGET_EXHAUSTED"),
}

PROVIDER_USAGE_FIELDS = frozenset(field for field, _reason in PROVIDER_LIMITS.values())
RESOURCE_USAGE_KEYS = frozenset({"provider_id", "receipt_id", *PROVIDER_USAGE_FIELDS})


def validate_budget(budget: dict | None) -> dict:
    if budget is not None and not isinstance(budget, dict):
        raise TypeError("budget must be an object")
    normalized = dict(budget or {})
    for key, minimum in BUDGET_LIMIT_MINIMUMS.items():
        if key not in normalized:
            continue
        value = normalized[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{key} must be an integer >= {minimum}")
    return normalized


def provider_usage_required(budget: dict | None) -> bool:
    value = budget or {}
    return any(key in value for key in PROVIDER_LIMITS)


def validate_resource_usage(data: dict | None, *, required: bool) -> dict | None:
    if data is None:
        if required:
            raise ValueError("resource_usage is required by the declared provider-metered executive budget")
        return None
    if not isinstance(data, dict):
        raise TypeError("data must be an object")

    raw = data.get("resource_usage")
    if raw is None:
        if required:
            raise ValueError("resource_usage is required by the declared provider-metered executive budget")
        return None
    if not isinstance(raw, dict):
        raise TypeError("resource_usage must be an object")

    unknown = set(raw) - RESOURCE_USAGE_KEYS
    if unknown:
        raise ValueError(f"unsupported resource_usage field: {sorted(unknown)[0]}")

    provider_id = raw.get("provider_id")
    receipt_id = raw.get("receipt_id")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("resource_usage.provider_id must be a non-empty string")
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise ValueError("resource_usage.receipt_id must be a non-empty string")

    present = [field for field in PROVIDER_USAGE_FIELDS if field in raw]
    if not present:
        raise ValueError("resource_usage must contain at least one supported resource dimension")

    normalized: dict[str, Any] = {
        "provider_id": provider_id.strip(),
        "receipt_id": receipt_id.strip(),
    }
    for field in sorted(PROVIDER_USAGE_FIELDS):
        if field not in raw:
            continue
        value = raw[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"resource_usage.{field} must be an integer >= 0")
        normalized[field] = value
    return normalized


def collect_provider_usage(events: list[dict]) -> dict:
    totals = {field: 0 for field in PROVIDER_USAGE_FIELDS}
    receipt_pairs: set[tuple[str, str]] = set()
    receipt_count = 0
    invalid_count = 0
    duplicate_count = 0

    for event in events:
        data = event.get("data") or {}
        if not isinstance(data, dict) or "resource_usage" not in data:
            continue
        try:
            usage = validate_resource_usage(data, required=False)
        except (TypeError, ValueError):
            invalid_count += 1
            continue
        if usage is None:
            continue
        pair = (usage["provider_id"], usage["receipt_id"])
        if pair in receipt_pairs:
            duplicate_count += 1
        else:
            receipt_pairs.add(pair)
        receipt_count += 1
        for field in PROVIDER_USAGE_FIELDS:
            totals[field] += int(usage.get(field, 0))

    return {
        "totals": totals,
        "receipt_pairs": receipt_pairs,
        "receipt_count": receipt_count,
        "invalid_count": invalid_count,
        "duplicate_count": duplicate_count,
    }


class ExecutiveResourceAccountingMixin:
    """Evidence-backed resource accounting layered over the preserved alpha.19 core."""

    def _executive_budget_state(self, tr: dict) -> dict:
        base = super()._executive_budget_state(tr)
        budget = dict(tr.get("budget") or {})
        metrics = dict(tr.get("metrics") or {})
        events = [self._executive_event_row(row) for row in self.store.executive_events(tr["id"])]
        provider = collect_provider_usage(events)

        consumed = dict(base.get("consumed") or {})
        consumed.update(provider["totals"])

        started_ns = metrics.get("wall_started_ns")
        if isinstance(started_ns, int) and not isinstance(started_ns, bool) and started_ns >= 0:
            wall_time_ms: int | None = max(0, time.time_ns() - started_ns) // 1_000_000
            wall_authority = "habitat-measured-host-wall-clock"
        else:
            wall_time_ms = None
            wall_authority = "unavailable"
        consumed["wall_time_ms"] = wall_time_ms

        limits = {key: budget[key] for key in BUDGET_LIMIT_MINIMUMS if key in budget}
        reasons = list(base.get("reasons") or [])

        if "max_wall_time_ms" in budget:
            if wall_time_ms is None:
                reasons.append("WALL_TIME_ACCOUNTING_UNAVAILABLE")
            elif wall_time_ms >= int(budget["max_wall_time_ms"]):
                reasons.append("WALL_TIME_BUDGET_EXHAUSTED")

        for limit_key, (usage_key, reason) in PROVIDER_LIMITS.items():
            if limit_key in budget and int(provider["totals"][usage_key]) >= int(budget[limit_key]):
                reasons.append(reason)

        required = provider_usage_required(budget)
        if required and provider["invalid_count"]:
            reasons.append("PROVIDER_USAGE_ACCOUNTING_INVALID")
        if required and provider["duplicate_count"]:
            reasons.append("PROVIDER_USAGE_RECEIPT_REPLAYED")

        recognized = set(BUDGET_LIMIT_MINIMUMS)
        unmetered = {key: value for key, value in budget.items() if key not in recognized}
        reasons = list(dict.fromkeys(reasons))
        return {
            **base,
            "limits": limits,
            "consumed": consumed,
            "accounting": {
                "wall_time": wall_authority,
                "provider_usage": "provider-reported-hash-chained",
                "provider_usage_required": required,
                "receipt_count": int(provider["receipt_count"]),
                "invalid_receipt_count": int(provider["invalid_count"]),
                "duplicate_receipt_count": int(provider["duplicate_count"]),
            },
            "exhausted": bool(reasons),
            "reasons": reasons,
            "unmetered": unmetered,
            "claim_boundary": (
                "Hard enforcement meters executive steps, failures, strategy switches and Habitat host-wall-clock time. "
                "Tool/token/compute usage is provider-reported, provenance-identified and hash-chained; Habitat validates "
                "and enforces those reports but does not independently verify provider billing telemetry. Host wall-clock "
                "measurement is not a distributed monotonic-clock guarantee."
            ),
        }

    def executive_start(
        self,
        goal: str,
        *,
        agent_id: str | None = None,
        episode_id: str | None = None,
        budget: dict | None = None,
        initial_strategy: str = "direct-analysis",
    ) -> dict:
        normalized_budget = validate_budget(budget)
        wall_started_ns = time.time_ns()
        result = super().executive_start(
            goal,
            agent_id=agent_id,
            episode_id=episode_id,
            budget=normalized_budget,
            initial_strategy=initial_strategy,
        )
        trajectory_id = result["id"]
        row = self.store.executive_trajectory(trajectory_id)
        metrics = dict(self._executive_row(row).get("metrics") or {})
        metrics["wall_started_ns"] = wall_started_ns
        self.store.update_executive_trajectory(trajectory_id, metrics=metrics, updated_at=utc_now())
        return self.executive_status(trajectory_id)

    def executive_advance(
        self,
        trajectory_id: str,
        phase: str,
        operation: str,
        *,
        status: str = "passed",
        progress: bool = False,
        ref_id: str | None = None,
        data: dict | None = None,
    ) -> dict:
        tr = self._require_active_trajectory(trajectory_id)
        phase_name = str(phase).upper()
        if phase_name not in EXECUTIVE_PHASES:
            raise ValueError("unsupported executive phase")
        if phase_name == "CLOSE":
            raise ValueError("use workspace.executive.complete for CLOSE")
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("operation must be non-empty")
        if status not in {"running", "passed", "failed", "inconclusive"}:
            raise ValueError("invalid executive step status")
        if data is not None and not isinstance(data, dict):
            raise TypeError("data must be an object")

        budget_before = self._executive_budget_state(tr)
        if budget_before["exhausted"]:
            raise RuntimeError(f"executive budget exhausted: {budget_before['reasons'][0]}")

        usage = validate_resource_usage(data, required=provider_usage_required(tr.get("budget")))
        if usage is not None:
            prior_events = [self._executive_event_row(row) for row in self.store.executive_events(trajectory_id)]
            prior = collect_provider_usage(prior_events)
            pair = (usage["provider_id"], usage["receipt_id"])
            if pair in prior["receipt_pairs"]:
                raise ValueError("resource_usage receipt identity has already been admitted on this trajectory")

        return super().executive_advance(
            trajectory_id,
            phase_name,
            operation,
            status=status,
            progress=progress,
            ref_id=ref_id,
            data=data,
        )


__all__ = [
    "BUDGET_LIMIT_MINIMUMS",
    "ExecutiveResourceAccountingMixin",
    "PROVIDER_LIMITS",
    "collect_provider_usage",
    "provider_usage_required",
    "validate_budget",
    "validate_resource_usage",
]

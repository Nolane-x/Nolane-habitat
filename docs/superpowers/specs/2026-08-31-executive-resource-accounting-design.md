# Executive Resource Accounting Design

## Context

Foundation Convergence is certified on `main`, but Habitat 0.1.0-alpha.19 still states that Executive Trajectory hard-enforces only executive steps, failed steps, and strategy switches. Other declared token/tool/time/compute budget fields are preserved as unmetered values. That makes the budget object structurally broader than the accounting evidence actually enforced.

This change closes that gap without changing the alpha.19 protocol method catalog or adding a second resource database.

## Goal

Make Executive Trajectory resource budgets evidence-backed and fail-closed for five additional resource dimensions while preserving the existing source/protocol/recovery boundaries:

- `max_wall_time_ms`
- `max_tool_calls`
- `max_input_tokens`
- `max_output_tokens`
- `max_compute_ms`

The existing limits remain unchanged:

- `max_steps`
- `max_failed_steps`
- `max_strategy_switches`

## Non-goals

- Do not infer or fabricate model token counts.
- Do not call provider-reported usage independently verified.
- Do not add a new public protocol method in alpha.19.
- Do not change the 12-tool MCP catalog.
- Do not add a new SQLite table or storage migration.
- Do not count arbitrary Habitat events as model/tool usage.
- Do not make Observatory authoritative for accounting.

## Chosen architecture

### 1. Resource usage rides on existing executive control events

`HabitatWorkspace.executive_advance(..., data=...)` already accepts an extensible data object and that data is part of the append-only executive event hash chain. A control step may therefore carry:

```json
{
  "resource_usage": {
    "provider_id": "provider-name",
    "receipt_id": "provider-receipt-id",
    "tool_calls": 1,
    "input_tokens": 1200,
    "output_tokens": 320,
    "compute_ms": 850
  }
}
```

No new public protocol method is required because the existing `workspace.executive.advance` surface already transports `data`.

### 2. Authority boundary

`wall_time_ms` is Habitat-measured from a trajectory-local persisted epoch-nanosecond start marker and the current host wall clock. It is a local process/host measurement, not a distributed monotonic-clock guarantee.

`tool_calls`, `input_tokens`, `output_tokens`, and `compute_ms` are provider-reported usage. Habitat validates, binds, hashes, accumulates, and enforces the report; Habitat does not claim independent verification of the provider's numbers.

The budget state must expose this distinction explicitly.

### 3. Fail-closed coverage

If any provider-metered limit is declared (`max_tool_calls`, `max_input_tokens`, `max_output_tokens`, or `max_compute_ms`), every admitted `executive_advance` control event must contain one valid `resource_usage` object.

A usage object must:

- contain non-empty string `provider_id`;
- contain non-empty string `receipt_id`;
- contain only the supported numeric resource dimensions plus the two identity fields;
- represent each supplied resource dimension as a non-boolean integer `>= 0`;
- contain at least one supported resource dimension;
- use a `(provider_id, receipt_id)` pair that has not already been admitted on the trajectory.

This does not prove the provider reported truthfully; it prevents Habitat from silently treating absent accounting as zero accounting.

### 4. Consumption is derived from the tamper-evident event chain

Provider-metered resource totals are derived from the complete executive event list, not from mutable trajectory metrics. A chain edit therefore invalidates trajectory assurance and cannot silently rewrite accounting history.

`steps`, `failed_steps`, and `strategy_switches` continue using existing trajectory metrics for backward compatibility.

### 5. Wall-time accounting

At `executive_start`, Habitat persists `wall_started_ns = time.time_ns()` in trajectory metrics. Current wall consumption is:

```text
max(0, time.time_ns() - wall_started_ns) // 1_000_000
```

If `max_wall_time_ms` is declared, budget evaluation hard-enforces it before a new executive control step. The explicit stop path remains available after exhaustion.

Wall time includes elapsed real time while the trajectory remains active, including process restarts. Host clock adjustment is a documented limitation; negative deltas clamp to zero rather than creating negative consumption.

### 6. Exhaustion semantics

Budget exhaustion reasons are deterministic names:

- `STEP_BUDGET_EXHAUSTED`
- `FAILURE_BUDGET_EXHAUSTED`
- `STRATEGY_SWITCH_BUDGET_EXHAUSTED`
- `WALL_TIME_BUDGET_EXHAUSTED`
- `TOOL_CALL_BUDGET_EXHAUSTED`
- `INPUT_TOKEN_BUDGET_EXHAUSTED`
- `OUTPUT_TOKEN_BUDGET_EXHAUSTED`
- `COMPUTE_BUDGET_EXHAUSTED`

An admitted step may consume the final allowed unit and leave the trajectory exhausted afterward, matching the existing step-budget behavior. Subsequent control advances fail before mutation. `workspace.executive.stop` remains the governed terminal path.

### 7. Compatibility

The alpha.19 protocol method catalog remains unchanged. Existing budget objects that use only the three historical hard limits behave exactly as before.

Unknown budget keys remain preserved under `unmetered` for backward compatibility, but the five new supported keys must no longer appear there.

The emitted executive trajectory schema remains backward-compatible through `additionalProperties: true`, but the schema will document the new budget-state accounting fields.

## Budget-state shape

`budget_state` extends the current object with:

```json
{
  "limits": {},
  "consumed": {
    "steps": 0,
    "failed_steps": 0,
    "strategy_switches": 0,
    "wall_time_ms": 0,
    "tool_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "compute_ms": 0
  },
  "accounting": {
    "wall_time": "habitat-measured-host-wall-clock",
    "provider_usage": "provider-reported-hash-chained",
    "provider_usage_required": false,
    "receipt_count": 0
  },
  "exhausted": false,
  "reasons": [],
  "strategy_switch_exhausted": false,
  "unmetered": {},
  "claim_boundary": "..."
}
```

## Validation and error handling

`executive_start` validates every recognized max-resource value as a non-boolean integer with the following minima:

- `max_steps >= 1`
- every other recognized max limit `>= 0`

`executive_advance` validates `resource_usage` before appending any event. Invalid/missing provider accounting fails without mutating trajectory events or metrics.

Duplicate `(provider_id, receipt_id)` pairs fail before mutation to prevent replay/double counting.

## Testing

RED tests must prove the feature is absent before production changes. The focused suite will cover:

1. provider-metered budget requires usage evidence;
2. valid usage is accumulated from events and exhausts the declared limit;
3. invalid negative/boolean/unknown usage fields fail before mutation;
4. duplicate provider receipt identity is rejected without increasing consumption;
5. wall time is Habitat-measured and can exhaust a trajectory deterministically with patched `time.time_ns`;
6. unknown historical budget keys remain `unmetered`;
7. the existing alpha.19 protocol method catalog is unchanged;
8. emitted trajectory objects remain schema-valid;
9. event-chain tampering still invalidates assurance, including resource-bearing events.

After focused GREEN, the exact branch head must pass the full Habitat CI matrix, recovery/fault gates, semantic precision, Foundation Convergence active certification, reproducibility, Semgrep, quality gate, and CodeQL before merge. The merged SHA must then pass the same post-merge certification before completion is claimed.

## Claim boundary

This feature establishes governed accounting of Habitat-measured wall time and provider-reported tool/token/compute usage within Executive Trajectory. It does not independently verify provider billing/usage telemetry, establish distributed clock correctness, prove universal cost optimality, or imply AGI/model superiority.

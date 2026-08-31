# Executive Resource Accounting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Executive Trajectory with evidence-backed wall-time and provider-reported tool/token/compute accounting while preserving alpha.19 protocol compatibility and fail-closed budget semantics.

**Architecture:** Reuse `executive_advance(..., data=...)` as the accounting transport so resource usage is included in the existing append-only executive hash chain. Persist only the wall-clock start marker in trajectory metrics; derive provider usage from complete events and distinguish Habitat-measured wall time from provider-reported usage in `budget_state`.

**Tech Stack:** Python 3.10–3.14, `unittest`, SQLite-backed Habitat Store, JSON Schema, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-31-executive-resource-accounting-design.md`

## Global Constraints

- Do not add or remove alpha.19 protocol methods or MCP tools.
- Do not add a SQLite table or storage migration.
- Do not fabricate token/tool/compute usage.
- Provider usage must be labeled provider-reported and must carry `provider_id` plus `receipt_id`.
- Provider-metered limits fail closed when a control step omits required accounting.
- Wall time is Habitat-measured host wall-clock time and must not be described as a distributed monotonic-clock guarantee.
- Unknown historical budget keys remain preserved under `unmetered`.
- Existing `max_steps`, `max_failed_steps`, and `max_strategy_switches` behavior remains backward compatible.
- No production code before a clean focused RED is observed in CI.

---

### Task 1: RED resource-accounting contract

**Files:**
- Create: `tests/test_executive_resource_accounting.py`

**Interfaces:**
- Consumes: existing `HabitatWorkspace.executive_start`, `executive_advance`, `executive_status`, `executive_plan`.
- Produces: executable contract for the five new hard limits and `resource_usage` semantics.

- [ ] **Step 1: Write focused behavior tests**

Add tests that require:

```python
tr = ws.executive_start(
    "Bound provider work",
    budget={"max_tool_calls": 1, "max_input_tokens": 10, "max_output_tokens": 5, "max_compute_ms": 20},
)
```

and prove that `executive_advance(...)` without `data["resource_usage"]` raises before event/metric mutation.

Add a valid usage case:

```python
usage = {
    "provider_id": "provider-A",
    "receipt_id": "receipt-1",
    "tool_calls": 1,
    "input_tokens": 10,
    "output_tokens": 5,
    "compute_ms": 20,
}
```

Then assert `budget_state["consumed"]` exposes those exact totals, all four corresponding exhaustion reasons are present, and `accounting["provider_usage"] == "provider-reported-hash-chained"`.

Add validation tests for negative values, booleans, unknown usage keys, empty provider/receipt IDs, and duplicate `(provider_id, receipt_id)` replay. Capture event count before each rejected call and assert no event is appended.

Add wall-time test using:

```python
with mock.patch("habitat._workspace_core.time.time_ns", side_effect=[1_000_000_000, 1_000_000_000, 1_002_000_000]):
    tr = ws.executive_start("Bound wall time", budget={"max_wall_time_ms": 1})
    state = ws.executive_status(tr["id"])["budget_state"]
    assert state["consumed"]["wall_time_ms"] == 2
    assert "WALL_TIME_BUDGET_EXHAUSTED" in state["reasons"]
```

Adjust the exact patched call sequence to match observed calls while keeping the test deterministic.

Add compatibility assertions that an unknown key such as `{"max_custom_units": 7}` remains under `unmetered` and historical step-budget behavior still works.

Add a chain-integrity test that tampers with a resource-bearing event and asserts `trajectory_chain["valid"] is False`.

- [ ] **Step 2: Commit RED tests**

Commit only the new test file:

```bash
git add tests/test_executive_resource_accounting.py
git commit -m "test: define executive resource accounting contract"
```

- [ ] **Step 3: Open PR and verify RED**

Open a PR against `main` and require a clean failure attributable only to missing new resource-accounting behavior. Existing compile/release-identity gates must remain green. Do not write production code until this RED is observed.

---

### Task 2: GREEN recognized budget dimensions and usage validation

**Files:**
- Modify: `habitat/_workspace_core.py`
- Test: `tests/test_executive_resource_accounting.py`

**Interfaces:**
- Produces recognized budget keys:
  - `max_wall_time_ms`
  - `max_tool_calls`
  - `max_input_tokens`
  - `max_output_tokens`
  - `max_compute_ms`
- Produces validated `resource_usage` payload contract.

- [ ] **Step 1: Extend start-time budget validation**

Create one canonical mapping near the executive helpers:

```python
_EXECUTIVE_BUDGET_LIMITS = {
    "max_steps": 1,
    "max_failed_steps": 0,
    "max_strategy_switches": 0,
    "max_wall_time_ms": 0,
    "max_tool_calls": 0,
    "max_input_tokens": 0,
    "max_output_tokens": 0,
    "max_compute_ms": 0,
}
```

Validate every present recognized key as a non-boolean integer at or above its minimum. Preserve unknown keys unchanged.

Persist `wall_started_ns=time.time_ns()` inside trajectory metrics at creation.

- [ ] **Step 2: Add a narrow usage parser/validator**

Add a helper that accepts a `data` object and the trajectory budget. Its provider usage shape is exactly:

```python
{
    "provider_id": str,
    "receipt_id": str,
    "tool_calls": int >= 0,
    "input_tokens": int >= 0,
    "output_tokens": int >= 0,
    "compute_ms": int >= 0,
}
```

At least one numeric resource field must exist. Unknown keys fail. Booleans fail even though `bool` subclasses `int` in Python.

If the trajectory declares any provider-metered max limit, absence of `resource_usage` on an `executive_advance` control event raises `ValueError` before mutation.

- [ ] **Step 3: Reject duplicate receipt identities before mutation**

Scan the complete trajectory events for prior `data.resource_usage` objects and reject a reused `(provider_id, receipt_id)` pair before appending the new event.

- [ ] **Step 4: Run focused GREEN**

Run the focused test module and existing alpha.14 executive tests. Fix implementation only, never weaken the contract.

- [ ] **Step 5: Commit**

```bash
git add habitat/_workspace_core.py tests/test_executive_resource_accounting.py
git commit -m "feat: validate executive resource accounting"
```

---

### Task 3: GREEN event-derived consumption and hard exhaustion

**Files:**
- Modify: `habitat/_workspace_core.py`
- Test: `tests/test_executive_resource_accounting.py`

**Interfaces:**
- Produces extended `budget_state.consumed`, `budget_state.accounting`, deterministic exhaustion reasons, and backward-compatible `unmetered`.

- [ ] **Step 1: Derive provider consumption from complete events**

In `_executive_budget_state`, obtain the complete trajectory event set for resource accounting. If keeping the helper static prevents event access, change it to an instance method and update all call sites.

Aggregate only validated `resource_usage` data from executive events:

```python
provider_totals = {
    "tool_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "compute_ms": 0,
}
```

Do not duplicate these totals into mutable trajectory metrics.

- [ ] **Step 2: Compute Habitat wall time**

Use persisted `metrics["wall_started_ns"]` and current `time.time_ns()`:

```python
wall_time_ms = max(0, time.time_ns() - started_ns) // 1_000_000
```

If old trajectories lack `wall_started_ns`, expose wall time as `None` and do not fabricate a value. A declared `max_wall_time_ms` on such an old trajectory must fail closed with an explicit accounting-unavailable reason rather than treating missing measurement as zero.

- [ ] **Step 3: Add resource exhaustion reasons**

For each declared resource max, compare the corresponding measured/reported consumption and append the exact reason from the spec. Keep the existing threshold behavior: consuming the final allowed unit leaves the trajectory exhausted for the next step.

- [ ] **Step 4: Expose accounting authority**

Return:

```python
"accounting": {
    "wall_time": "habitat-measured-host-wall-clock" or "unavailable",
    "provider_usage": "provider-reported-hash-chained",
    "provider_usage_required": bool(...),
    "receipt_count": int,
}
```

Update `claim_boundary` so it explicitly denies independent provider-usage verification and distributed monotonic-clock guarantees.

- [ ] **Step 5: Run focused GREEN and alpha.14 regressions**

Require all new tests plus `tests/test_alpha14_executive_trajectory.py` to pass.

- [ ] **Step 6: Commit**

```bash
git add habitat/_workspace_core.py tests/test_executive_resource_accounting.py
git commit -m "feat: enforce executive resource budgets"
```

---

### Task 4: Machine contract and documentation closure

**Files:**
- Modify: `schemas/executive-trajectory.schema.json`
- Modify: `docs/IMPLEMENTATION-STATUS.md`
- Modify: `docs/LIMITATIONS.md`
- Test: `tests/test_executive_resource_accounting.py`
- Test: existing release identity/schema suites

**Interfaces:**
- Produces machine/documentation truth matching runtime behavior.

- [ ] **Step 1: Tighten schema documentation without breaking old objects**

Document `budget_state.accounting`, extended consumed dimensions, and `unmetered`. Keep `additionalProperties: true` and do not require fields that would invalidate historical serialized alpha.14 objects unless emitted current objects always contain them.

- [ ] **Step 2: Update implementation status**

Replace the statement that token/tool/time/compute are wholly unmetered with the exact implemented boundary: wall time is Habitat-measured; provider tool/token/compute reports are provenance-identified, hash-chained, required when corresponding hard limits are declared, and not independently verified.

- [ ] **Step 3: Update limitations**

Replace `Executive budgets are only partially metered` with a narrower limitation that documents provider-report trust and host-clock caveats. Do not claim billing accuracy, complete model instrumentation, or distributed clock correctness.

- [ ] **Step 4: Verify protocol/release identity did not drift**

Run contract/protocol/release-identity suites. The alpha.19 method catalog and MCP tool catalog must be unchanged.

- [ ] **Step 5: Commit**

```bash
git add schemas/executive-trajectory.schema.json docs/IMPLEMENTATION-STATUS.md docs/LIMITATIONS.md tests/test_executive_resource_accounting.py
git commit -m "docs: close executive resource accounting boundary"
```

---

### Task 5: Exact-head certification and merge

**Files:**
- No additional production files unless a real verification failure requires a fix through a new RED→GREEN cycle.

**Interfaces:**
- Produces certified PR head and certified merged `main` SHA.

- [ ] **Step 1: Require exact-head Habitat CI GREEN**

Require Ubuntu/Windows × Python 3.10/3.14 success for:

- full regression suite;
- semantic precision evidence;
- Foundation Convergence active certification;
- foundation baseline/scale evidence;
- isolated regression matrix;
- protocol/contract compatibility;
- DB recovery;
- mutation recovery;
- fault injection/reliability;
- reproducible build;
- distribution verification;
- Semgrep;
- quality gate;
- artifact upload.

- [ ] **Step 2: Require exact-head CodeQL GREEN**

Both Python and JavaScript/TypeScript must succeed.

- [ ] **Step 3: Review final diff and drift**

Verify PR head, changed-file scope, comments/reviews, mergeability, and fresh `main` SHA. If `main` drifted, integrate deliberately and re-run exact-head certification because the candidate tree changed.

- [ ] **Step 4: Merge with exact-head guard**

Use a normal GitHub merge commit with expected-head protection.

- [ ] **Step 5: Require post-merge Habitat CI and CodeQL GREEN**

Run the same certification on the actual merge SHA. Read at least one uploaded artifact and verify `source_commit == checkout_commit == merge_sha` and Foundation Convergence remains `12/12`.

- [ ] **Step 6: Claim completion only after post-merge evidence**

Report exact candidate SHA, merge SHA, CI/CodeQL run IDs, fresh test count, resource-accounting behavior, and the bounded claim. Do not call provider usage independently verified.

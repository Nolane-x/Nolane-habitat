# Controlled Benchmark Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Foundation Convergence Wave 4 controlled Habitat-vs-filesystem experiments and explicit internal ablations first-class, deterministic, causally bound, and independently evaluable.

**Architecture:** Extend the pure `habitat.benchmarking` domain layer rather than creating another runner. A deterministic immutable experiment plan produces exact run manifests for the filesystem control, Habitat ON, and each requested Habitat ablation. Evidence admission requires an explicit receipt carrying the exact planned-run identity and environment fingerprint, because `BenchmarkRun` alone does not encode enough experiment/environment identity to prove causal membership. Comparisons preserve unavailable measurements as unavailable. The existing `benchmarks/agent_ab_harness.py` remains wire/CLI compatible and will be adapted to these contracts in a following Wave 4 slice after the reusable kernel is certified.

**Tech Stack:** Python 3.10+, frozen dataclasses, stdlib `hashlib`/`random`, `unittest`, existing `habitat.benchmarking` types.

**Spec:** `docs/design/FOUNDATION-CONVERGENCE.md` sections 7 and 12 Wave 4; `benchmarks/AGENT-AB-BENCHMARK-CONTRACT.md`.

## Global Constraints

- Preserve alpha.19 public protocol, MCP, workspace, Store, and existing schema-3 A/B harness behavior.
- Same model, scaffold, repository/task spec, evaluator identity, environment fingerprint, retry/repetition controls, and deterministic seed must be causally explicit.
- Minimum controlled benchmark repetition count is 3 per task/condition.
- Filesystem control and Habitat ON are always present; internal ablations are Habitat-only conditions.
- Missing measurements remain `None`; they must never be treated as measured zero.
- An agent self-report is never an independent success verdict.
- No new third-party runtime dependency.
- RED must be observed before each production implementation; exact-head full CI and CodeQL gate every merge.

---

### Task 1: Deterministic Experiment Plan and Run Manifest

**Files:**
- Create: `habitat/benchmarking/experiment.py`
- Modify: `habitat/benchmarking/__init__.py`
- Test: `tests/test_benchmark_experiment.py`

**Interfaces:**
- Consumes: `BenchmarkSpec`, `AblationConfig`, `BenchmarkArm`.
- Produces: `PlannedRun` and `ExperimentPlan`.

```python
@dataclass(frozen=True)
class PlannedRun:
    experiment_id: str
    spec_fingerprint: str
    condition_id: str
    arm: BenchmarkArm
    repetition: int
    seed: int
    model_id: str
    scaffold_id: str
    evaluator_id: str
    environment_fingerprint: str
    ablation: AblationConfig = AblationConfig()

    @property
    def identity(self) -> str: ...


@dataclass(frozen=True)
class ExperimentPlan:
    experiment_id: str
    spec: BenchmarkSpec
    model_id: str
    scaffold_id: str
    evaluator_id: str
    environment_fingerprint: str
    seeds: tuple[int, ...]
    habitat_ablations: tuple[AblationConfig, ...] = ()

    @property
    def repetitions(self) -> int: ...

    @property
    def conditions(self) -> tuple[tuple[str, str, AblationConfig], ...]: ...

    def planned_runs(self) -> tuple[PlannedRun, ...]: ...
```

Conditions are exactly:
1. `filesystem` with default/no ablation;
2. `habitat` with default/no ablation;
3. one Habitat condition per unique requested non-default ablation, identified by its ablation fingerprint.

For each repetition, condition execution order is deterministically shuffled with a stable SHA-256-derived random seed from `experiment_id`, task spec fingerprint, and repetition seed. Rebuilding the same plan must return identical order and identities. Different causal controls must change run identity.

- [ ] **Step 1: Write failing tests** requiring minimum/unique/non-negative integer seeds, non-empty causal identities, no default/duplicate explicit ablations, complete condition coverage, deterministic shuffle, and causal identity sensitivity.
- [ ] **Step 2: Verify RED** with `python -m unittest tests.test_benchmark_experiment -v`; expected missing `PlannedRun` / `ExperimentPlan` exports only.
- [ ] **Step 3: Implement minimal immutable experiment planning** using deterministic JSON/SHA-256 fingerprint conventions; never Python `hash()`.
- [ ] **Step 4: Verify focused GREEN and regression** with focused unittest and full discovery.
- [ ] **Step 5: Commit** as `feat: add deterministic benchmark experiment planning`.

---

### Task 2: Planned-Result Receipt Admission and Experiment Completeness

**Files:**
- Modify: `habitat/benchmarking/experiment.py`
- Modify: `habitat/benchmarking/__init__.py`
- Test: `tests/test_benchmark_experiment.py`

**Rationale:** `BenchmarkResult` binds a task spec, run, evaluator, model/scaffold, seed, arm, repetition, and ablation, but it does not independently prove which experiment/environment execution produced it. Admission therefore MUST NOT infer experiment membership merely from fields that happen to match. A first-class receipt binds the result to the exact `PlannedRun.identity` and exact environment fingerprint.

**Interfaces:**

```python
@dataclass(frozen=True)
class RecordedBenchmarkResult:
    planned_run_identity: str
    environment_fingerprint: str
    result: BenchmarkResult


@dataclass(frozen=True)
class ExperimentEvidence:
    plan: ExperimentPlan
    records: tuple[RecordedBenchmarkResult, ...]

    @property
    def complete(self) -> bool: ...

    @property
    def missing_run_identities(self) -> tuple[str, ...]: ...


def admit_experiment_results(
    plan: ExperimentPlan,
    records: Iterable[RecordedBenchmarkResult],
) -> ExperimentEvidence: ...
```

Admission is fail-closed. Every receipt must identify an exact planned run, and the admitted result must independently agree with that plan on:
- environment fingerprint;
- benchmark spec fingerprint;
- arm and derived condition;
- repetition and seed;
- model and scaffold;
- ablation;
- evaluator identity.

Admission must reject an unknown planned identity, duplicate planned identity, another environment, another spec, model/scaffold/evaluator mismatch, unplanned repetition/seed/arm/ablation, impossible filesystem ablation, and non-receipt inputs. Agent self-report is preserved only as data and never substitutes for the independent evaluator verdict.

Partial evidence is valid and reports exact missing planned identities in deterministic plan order. Completion becomes true only when every planned condition/repetition has exactly one admitted independently evaluated receipt.

- [ ] **Step 1: Write failing admission tests** for partial/complete evidence, receipt immutability, all causal mismatches, duplicates, invalid inputs, and independent-evaluator authority.
- [ ] **Step 2: Verify RED** with focused/full unittest and confirm missing receipt/admission exports are the only failure.
- [ ] **Step 3: Implement fail-closed receipt admission** without deriving missing causal identity from metrics or self-reports.
- [ ] **Step 4: Verify focused GREEN and full regression**.
- [ ] **Step 5: Commit** as `feat: admit benchmark evidence against exact plans`.

---

### Task 3: Causal Pairing and Missingness-Safe Metric Deltas

**Files:**
- Modify: `habitat/benchmarking/experiment.py`
- Modify: `habitat/benchmarking/__init__.py`
- Test: `tests/test_benchmark_experiment.py`

**Interfaces:**
- Consumes: complete or partial `ExperimentEvidence` receipts.
- Produces: immutable `MetricDelta`, `ConditionComparison`, and `compare_conditions`.

The final Task 3 RED contract will preserve per-repetition distributions rather than collapse them into one headline. Comparisons pair only receipts from the same repetition/seed. Requested conditions must exist in the plan. A metric delta is unavailable whenever either side is unavailable; explicit measured zero remains zero. No statistical superiority claim is generated by this kernel.

- [ ] **Step 1: Write failing comparison tests** requiring exact causal pairing, per-repetition independent success deltas, unavailable-vs-zero preservation, unknown-condition rejection, immutable deterministic output, and partial-evidence behavior.
- [ ] **Step 2: Verify RED** and confirm only the new comparison API is missing/failing.
- [ ] **Step 3: Implement minimal comparison layer** with raw pair-level evidence only.
- [ ] **Step 4: Verify exact-head readiness** with focused test, full regression, repository CI matrix, CodeQL, review/thread audit, changed-file boundary, and main-drift check.
- [ ] **Step 5: Commit** as `feat: add causal benchmark condition comparisons`.

## Self-Review

- Spec coverage: this slice makes controlled experiments and all Foundation-required ablation dimensions runnable as immutable plans, admits only causally comparable independently evaluated receipts, and provides raw paired deltas. Harness adaptation and held-out suite population remain later Wave 4 tasks, explicitly outside this kernel slice.
- Causal binding: environment/experiment membership is explicit through `RecordedBenchmarkResult`; raw `BenchmarkResult` matching is insufficient by design.
- Placeholder scan: no TBD/TODO/implicit error-handling steps.
- Type consistency: all new APIs consume the Wave 4A immutable contracts and preserve their `None` measurement semantics.
- Compatibility: no existing protocol, workspace, storage, release, or schema-3 harness surface is modified by this slice.

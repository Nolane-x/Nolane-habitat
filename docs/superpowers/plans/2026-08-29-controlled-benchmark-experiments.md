# Controlled Benchmark Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Foundation Convergence Wave 4 controlled Habitat-vs-filesystem experiments and explicit internal ablations first-class, deterministic, causally bound, and independently evaluable.

**Architecture:** Extend the pure `habitat.benchmarking` domain layer rather than creating another runner. A deterministic immutable experiment plan produces exact run manifests for the filesystem control, Habitat ON, and each requested Habitat ablation. A separate evidence-admission layer accepts only results that were actually planned, preserves evaluator independence, and computes deltas without converting unavailable measurements into zero. The existing `benchmarks/agent_ab_harness.py` remains wire/CLI compatible and will be adapted to these contracts in a following Wave 4 slice after the reusable kernel is certified.

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

`PlannedRun` fields:
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
```

`ExperimentPlan` fields and API:
```python
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

- [ ] **Step 1: Write failing tests**

Tests must require:
- fewer than 3 seeds rejected;
- negative, boolean, and duplicate seeds rejected;
- empty causal identity strings rejected;
- duplicate/default entries in `habitat_ablations` rejected rather than silently weakening the experiment;
- filesystem + Habitat ON always present;
- every requested explicit ablation present exactly once per repetition and only under Habitat;
- deterministic randomized order and stable run identities;
- changing model/scaffold/evaluator/environment/spec/seed/ablation changes the relevant planned identity.

- [ ] **Step 2: Verify RED**

Run:
```bash
python -m unittest tests.test_benchmark_experiment -v
```
Expected: FAIL because `PlannedRun` / `ExperimentPlan` are not exported.

- [ ] **Step 3: Implement minimal immutable experiment planning**

Use the existing deterministic JSON/SHA-256 fingerprint conventions from `habitat/benchmarking/model.py`. Do not use Python's process-randomized `hash()`.

- [ ] **Step 4: Verify focused GREEN and regression**

Run:
```bash
python -m unittest tests.test_benchmark_experiment -v
python -m unittest discover -s tests -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add habitat/benchmarking/experiment.py habitat/benchmarking/__init__.py tests/test_benchmark_experiment.py
git commit -m "feat: add deterministic benchmark experiment planning"
```

---

### Task 2: Planned-Result Admission and Experiment Completeness

**Files:**
- Modify: `habitat/benchmarking/experiment.py`
- Modify: `habitat/benchmarking/__init__.py`
- Test: `tests/test_benchmark_experiment.py`

**Interfaces:**
- Consumes: `ExperimentPlan`, `PlannedRun`, `BenchmarkResult`.
- Produces: `ExperimentEvidence` and `admit_experiment_results`.

```python
@dataclass(frozen=True)
class ExperimentEvidence:
    plan: ExperimentPlan
    results: tuple[BenchmarkResult, ...]

    @property
    def complete(self) -> bool: ...

    @property
    def missing_run_identities(self) -> tuple[str, ...]: ...


def admit_experiment_results(
    plan: ExperimentPlan,
    results: Iterable[BenchmarkResult],
) -> ExperimentEvidence: ...
```

Admission must fail closed for:
- a result bound to another spec;
- model or scaffold mismatch;
- evaluator mismatch;
- repetition/seed/arm/ablation combination that was not planned;
- duplicate run identity;
- an impossible filesystem ablation.

Partial evidence is retained and reports exact missing planned identities; completion becomes true only when every planned condition/repetition has one admitted independent result.

- [ ] **Step 1: Write failing admission tests**

Include one valid partial evidence case, one exact complete case, and a subtest for every mismatch above.

- [ ] **Step 2: Verify RED**

Run focused unittest and confirm missing export/API failures only.

- [ ] **Step 3: Implement fail-closed admission**

Map results to planned runs using the same causal identity payload; never infer missing causal controls from metrics or self-reported success.

- [ ] **Step 4: Verify focused GREEN and full regression**

Run focused test then full `unittest discover`.

- [ ] **Step 5: Commit**

```bash
git add habitat/benchmarking/experiment.py habitat/benchmarking/__init__.py tests/test_benchmark_experiment.py
git commit -m "feat: admit benchmark evidence against exact plans"
```

---

### Task 3: Causal Pairing and Missingness-Safe Metric Deltas

**Files:**
- Modify: `habitat/benchmarking/experiment.py`
- Modify: `habitat/benchmarking/__init__.py`
- Test: `tests/test_benchmark_experiment.py`

**Interfaces:**
- Consumes: complete or partial `ExperimentEvidence`.
- Produces: `MetricDelta`, `ConditionComparison`, `compare_conditions`.

```python
@dataclass(frozen=True)
class MetricDelta:
    baseline: int | float | None
    candidate: int | float | None
    delta: int | float | None

@dataclass(frozen=True)
class ConditionComparison:
    baseline_condition_id: str
    candidate_condition_id: str
    repetitions_compared: int
    success_delta: int
    metric_deltas: dict[str, tuple[MetricDelta, ...]]


def compare_conditions(
    evidence: ExperimentEvidence,
    baseline_condition_id: str,
    candidate_condition_id: str,
) -> ConditionComparison: ...
```

Comparisons pair only the same repetition/seed. Requested conditions must exist in the plan. A metric delta is `None` whenever either side is unavailable. Do not create a single aggregate headline that hides per-run distribution.

- [ ] **Step 1: Write failing comparison tests**

Require exact causal pairing, per-repetition independent success deltas, unavailable-vs-zero preservation, unknown-condition rejection, and deterministic output order.

- [ ] **Step 2: Verify RED**

Run focused unittest and confirm only the new comparison API is missing/failing.

- [ ] **Step 3: Implement minimal comparison layer**

Compute only raw per-pair deltas and counts needed by the Foundation Convergence contract; no statistical superiority claim is generated here.

- [ ] **Step 4: Verify exact-head readiness**

Run:
```bash
python -m unittest tests.test_benchmark_experiment -v
python -m unittest discover -s tests -v
```
Then require repository CI matrix, CodeQL, review/thread audit, changed-file boundary, and main-drift check on the exact final head.

- [ ] **Step 5: Commit**

```bash
git add habitat/benchmarking/experiment.py habitat/benchmarking/__init__.py tests/test_benchmark_experiment.py
git commit -m "feat: add causal benchmark condition comparisons"
```

## Self-Review

- Spec coverage: this slice makes controlled experiments and all Foundation-required ablation dimensions runnable as immutable plans, admits only causally comparable independent results, and provides raw paired deltas. Harness adaptation and held-out suite population remain later Wave 4 tasks, explicitly outside this kernel slice.
- Placeholder scan: no TBD/TODO/implicit error-handling steps.
- Type consistency: all new APIs consume the Wave 4A immutable contracts and preserve their `None` measurement semantics.
- Compatibility: no existing protocol, workspace, storage, release, or schema-3 harness surface is modified by this slice.

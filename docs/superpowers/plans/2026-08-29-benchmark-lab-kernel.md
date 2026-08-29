# Wave 4A Benchmark Lab Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a first-class, deterministic Benchmark Lab domain kernel that gives all future Habitat benchmark runners one typed vocabulary for task classes, metrics, run identity, independent evaluation, evidence references, and subsystem ablations.

**Architecture:** Add a pure `habitat.benchmarking` package with no workspace, storage, protocol, subprocess, network, or filesystem dependency. The existing top-level `benchmarks/agent_ab_harness.py` remains the orchestration script in Wave 4A; a later slice will adapt its schema-3 dict reports into this kernel. Domain objects are immutable, validate invariants at construction, and expose deterministic SHA-256 fingerprints from canonical JSON-compatible fields so later paired/ablation aggregation can prove comparability instead of trusting labels.

**Tech Stack:** Python >=3.10, stdlib `dataclasses`, `hashlib`, `json`, `typing`; `unittest` for contracts.

**Spec:** `docs/design/FOUNDATION-CONVERGENCE.md` §7 and `benchmarks/AGENT-AB-BENCHMARK-CONTRACT.md`

## Global Constraints

- Preserve package/release identity `0.1.0-alpha.19`; Wave 4A is not a release/version change.
- Add no runtime dependency.
- Do not modify `HabitatWorkspace`, protocol methods, source-authority precedence, mutation/recovery semantics, Store/schema, or execution containment.
- Keep `benchmarks/agent_ab_harness.py` behavior and report schema 3 unchanged in Wave 4A.
- The kernel performs no I/O at import or construction time.
- Benchmark taxonomy is exactly: retrieval/orientation, semantic navigation, refactor/rename, debugging, multi-file implementation, test selection, runtime diagnosis, UI tasks, multi-agent invalidation, adversarial/authority tests, large repository scaling.
- Benchmark metrics must represent all §7.1 minimum measurements without conflating unavailable measurements with zero.
- Required ablation vocabulary must cover: no graph expansion, no residency prior, no memory, no runtime evidence, no executive strategy switching, parser-only semantics, precise-provider semantics, and static retrieval weights versus learned-policy candidate.
- Independent evaluator identity/outcome remains separate from agent self-report.
- Evidence references are immutable identifiers only; Wave 4A does not invent an evidence store.

---

### Task 1: Benchmark taxonomy and ablation contract

**Files:**
- Create: `habitat/benchmarking/__init__.py`
- Create: `habitat/benchmarking/model.py`
- Create: `tests/test_benchmark_lab.py`

**Interfaces:**
- Produces: `BENCHMARK_CLASSES`, `ABLATION_TARGETS`, `BenchmarkSpec`, `AblationConfig`.
- `BenchmarkSpec.fingerprint` and `AblationConfig.fingerprint` are deterministic lowercase SHA-256 hex strings.

- [ ] **Step 1: Write the failing import/domain contract**

Create tests that import `habitat.benchmarking`, require the exact 11-class taxonomy and five disable-able subsystem targets, require frozen dataclasses, reject empty/unknown identities, distinguish semantic mode (`default`, `parser_only`, `precise_provider`) and retrieval policy (`default`, `static`, `learned_candidate`), and prove equivalent ablation/spec values have equal fingerprints while materially different values do not.

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_benchmark_lab -v`

Expected: fail because `habitat.benchmarking` does not exist.

- [ ] **Step 3: Implement the minimal pure domain types**

`model.py` must use frozen dataclasses and canonical JSON hashing only. Validate strings as non-empty, taxonomy membership exactly, ablation targets against the closed set, and prohibit contradictory semantic/retrieval modes by representing each as one explicit mode rather than independent booleans.

- [ ] **Step 4: Run focused GREEN**

Run: `python -m unittest tests.test_benchmark_lab -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit production + tests together after RED evidence exists.

---

### Task 2: Normalized metric, run, evaluation, and result identity

**Files:**
- Modify: `habitat/benchmarking/model.py`
- Modify: `habitat/benchmarking/__init__.py`
- Modify: `tests/test_benchmark_lab.py`

**Interfaces:**
- Produces: `BenchmarkMetrics`, `BenchmarkRun`, `EvaluationResult`, `BenchmarkResult`.
- `BenchmarkMetrics` carries input/output tokens (nullable when unavailable), tool calls, exact-source bytes, context precision/recall proxies (nullable), irrelevant-object admission, wall time, ingest cost, warm reconcile cost, provider calls, failed/repeated strategies, verifications, rollbacks, and conflicts.
- `BenchmarkRun.identity` binds task fingerprint, repository revision, arm, repetition, seed, model identity, scaffold identity, and ablation fingerprint.
- `EvaluationResult` owns independent evaluator identity and success verdict; agent self-report is not a substitute.

- [ ] **Step 1: Write failing contracts**

Add tests that reject negative counts/timings, reject precision/recall proxies outside `[0, 1]`, preserve `None` as unavailable rather than coercing it to zero, reject empty model/scaffold/evaluator identities, prove run identity changes when any causal control changes, and require a result’s run to reference the same `BenchmarkSpec` fingerprint it wraps.

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_benchmark_lab -v`

Expected: failures for missing normalized metric/run/evaluation/result APIs.

- [ ] **Step 3: Implement minimal immutable records and validation**

Use no generic mutable metadata dictionaries. Evidence references are tuples of non-empty strings. Keep evaluator outcome separate from agent-claimed success. Do not aggregate effects or infer causality in this slice.

- [ ] **Step 4: Run focused GREEN and legacy harness regression**

Run:
- `python -m unittest tests.test_benchmark_lab -v`
- `python -m unittest tests.test_alpha9_benchmark_harness -v`

Expected: PASS with legacy harness behavior unchanged.

- [ ] **Step 5: Commit**

Commit the complete Wave 4A kernel.

---

### Task 3: Structural audit and exact-head certification

**Files:**
- No production expansion unless a test exposes a kernel defect.

**Interfaces:**
- Consumes the final Wave 4A candidate SHA.
- Produces merge evidence, not new runtime behavior.

- [ ] **Step 1: Audit scope**

Require changed files to stay within the plan, `habitat/benchmarking/`, and `tests/test_benchmark_lab.py`. Confirm no protocol/workspace/storage/version/harness drift and no I/O/runtime imports in the kernel.

- [ ] **Step 2: Focused regression**

Run benchmark-kernel tests and the existing Alpha.9 harness test.

- [ ] **Step 3: Exact-head CI**

Require Habitat CI across Ubuntu/Windows × Python 3.10/3.14 and CodeQL on the exact final SHA. Require all substantive release gates already enforced by the repository workflow.

- [ ] **Step 4: Review and drift audit**

Check PR review threads, changed files, head/base drift, and exact final SHA immediately before merge.

- [ ] **Step 5: Merge with exact-head lock**

Merge only with `expected_head_sha=<final candidate>` and verify `main` advances to the returned merge commit.

## Self-Review

- Spec coverage: §7.1 metrics are represented; §7.2 exact benchmark classes are represented; §7.3 required ablations are representable. Actual subsystem disabling and causal aggregation are intentionally deferred to later Wave 4 slices because they require runner/runtime integration and are independently reviewable.
- Contract coverage: model/scaffold/evaluator identity, separate ingest/warm/task costs, exact-source accounting, raw evidence references, repeated runs/seed identity, and independent verdict separation are represented without claiming a benchmark result exists.
- Placeholder scan: no TBD/TODO/future implementation placeholder appears in executable task steps.
- Type consistency: `BenchmarkSpec.fingerprint` is the task identity anchor; `AblationConfig.fingerprint` is included in `BenchmarkRun.identity`; `BenchmarkResult` verifies its wrapped run/spec binding.
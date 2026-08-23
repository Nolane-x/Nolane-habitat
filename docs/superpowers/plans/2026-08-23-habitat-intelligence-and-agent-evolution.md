# Nolane Habitat Intelligence and Agent Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Habitat's semantic evidence, context selection, project memory, multi-agent coordination, and Codex skills measurably more useful while preventing stale truth, private-state leakage, and circular self-improvement.

**Architecture:** Build a sealed semantic/context benchmark first, then add a shared provenance envelope, contradiction-aware memory lifecycle, evaluable context planner, deterministic coordination service, and Teacher–Student–Judge evolution gate. Keep all public MCP and protocol names stable; changes are additive or internal behind compatibility façades.

**Tech Stack:** Python 3.10+, SQLite, `unittest`, JSON fixtures, Habitat Semantic/Effect/Dataflow Twins, MCP Python SDK, Codex plugin skills.

**Spec:** `docs/superpowers/specs/2026-08-23-habitat-production-grade-evolution-design.md`

## Global Constraints

- Begin only after Truth Core Tasks 1–3 in `2026-08-23-habitat-comprehensive-hardening.md` pass.
- Preserve the `habitat.agent.v1alpha2` envelope and the compact 12-tool MCP surface.
- Every semantic fact emitted to an agent must bind provider, provider version, revision, source digest, trust, parse completeness, evidence, and invalidation keys.
- Training/discovery fixtures and sealed holdouts must be stored separately and scored separately.
- Parsed symbol precision must be at least 97%; parsed symbol recall at least 95%; relation precision at least 95%; relation recall at least 90% on the declared deterministic corpus.
- Changed-path stale-fact invalidation, context budget compliance, exact-source provenance, and cross-agent private-state isolation must each pass 100% of declared cases.
- No ranking or skill candidate may be admitted with a regression in safety, authorization, epistemics, integrity, or recovery.
- Raw private chain-of-thought and secrets are never benchmark inputs, persisted outputs, or Observatory content.

---

## File and interface map

| Unit | Responsibility | Stable interface introduced here |
|---|---|---|
| `habitat/semantic/benchmark.py` | load and score semantic corpus | `load_cases`, `score_case`, `aggregate_scores` |
| `habitat/provenance.py` | typed fact lineage and invalidation keys | `ProvenanceEnvelope`, `EvidenceRef`, `is_current` |
| `habitat/memory_lifecycle.py` | validate memory transitions and conflicts | `MemoryStatus`, `transition_memory`, `find_contradictions` |
| `habitat/context/evaluation.py` | score selected context under fixed budgets | `ContextEvaluationCase`, `ContextMetrics`, `evaluate_plan` |
| `habitat/context/policy.py` | versioned deterministic ranking policy | `RankingPolicy`, `PolicyComparison`, `compare_policies` |
| `habitat/coordination.py` | leases, observations, notifications, conflicts | `CoordinationService` |
| `habitat/session_bootstrap.py` | compact agent onboarding/checkpoint packet | `SessionBootstrap`, `build_bootstrap` |
| `habitat/evolution.py` | frozen Teacher–Student–Judge admission | `EvolutionRun`, `admit_candidate` |

## Task 1: Build a sealed semantic quality benchmark

**Files:**

- Create: `habitat/semantic/benchmark.py`
- Create: `benchmarks/corpus/semantic/discovery/manifest.json`
- Create: `benchmarks/corpus/semantic/holdout/manifest.json`
- Create: `benchmarks/run_semantic_quality.py`
- Create: `tests/test_semantic_benchmark.py`
- Modify: `pyproject.toml`

**Interfaces:**

- Consumes: `CompiledFile`, `Symbol`, `Relation`, and `Diagnostic` from existing compiler/model modules.
- Produces: `BenchmarkCase`, `SemanticScore`, `load_cases(root: Path)`, `score_case(case, actual)`, and `aggregate_scores(scores)`.

- [ ] **Step 1: Write failing manifest and scorer tests.**

```python
import unittest
from pathlib import Path

from habitat.semantic.benchmark import load_cases, score_case


class SemanticBenchmarkTests(unittest.TestCase):
    def test_holdout_case_scores_exact_symbols_and_relations(self) -> None:
        cases = load_cases(Path("benchmarks/corpus/semantic/holdout"))
        case = next(item for item in cases if item.case_id == "python-alias-delete-001")
        score = score_case(case, case.expected)
        self.assertEqual(1.0, score.symbol_precision)
        self.assertEqual(1.0, score.symbol_recall)
        self.assertEqual(1.0, score.relation_precision)
        self.assertEqual(1.0, score.relation_recall)
```

- [ ] **Step 2: Run the test and verify the module is absent.**

Run: `python -m unittest -v tests.test_semantic_benchmark`

Expected: FAIL with `ModuleNotFoundError: No module named 'habitat.semantic.benchmark'`.

- [ ] **Step 3: Implement immutable benchmark types and set-based scoring.**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExpectedSemantics:
    symbols: frozenset[str]
    relations: frozenset[tuple[str, str, str]]


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    language: str
    source_root: Path
    expected: ExpectedSemantics
    split: str


@dataclass(frozen=True)
class SemanticScore:
    case_id: str
    symbol_precision: float
    symbol_recall: float
    relation_precision: float
    relation_recall: float


def _precision_recall(expected: frozenset, actual: frozenset) -> tuple[float, float]:
    correct = len(expected & actual)
    precision = correct / len(actual) if actual else float(not expected)
    recall = correct / len(expected) if expected else float(not actual)
    return precision, recall
```

- [ ] **Step 4: Add deterministic fixtures.**

Create discovery and holdout cases for Python, JavaScript, TypeScript, CSS, JSON, and Markdown covering create, rename, delete, alias, overload, malformed syntax, minified same-line declarations, generated-file exclusion, cross-file relation, negative-space relation, and provider-unavailable degradation. Each manifest entry includes case ID, split, language, source files, expected stable symbol keys, expected relation triples, and expected diagnostics.

- [ ] **Step 5: Prevent holdout leakage.**

Hash each holdout manifest and source tree. `run_semantic_quality.py` refuses a holdout whose hash appears in a discovery run artifact or whose files are imported from the discovery directory.

- [ ] **Step 6: Add threshold aggregation.**

`aggregate_scores` reports micro and macro precision/recall, per-language scores, failures, fixture hashes, provider versions, and parse-completeness rates. Exit nonzero below the thresholds in Global Constraints.

- [ ] **Step 7: Verify and commit.**

Run: `python benchmarks/run_semantic_quality.py --split discovery --out .test-artifacts/semantic-discovery.json`

Run: `python benchmarks/run_semantic_quality.py --split holdout --out .test-artifacts/semantic-holdout.json`

Run: `python -m unittest -v tests.test_semantic_benchmark`

Commit: `git commit -m "test(semantic): add sealed quality benchmark"`

## Task 2: Attach complete provenance and invalidation to semantic facts

**Files:**

- Create: `habitat/provenance.py`
- Modify: `habitat/model.py`
- Modify: `habitat/compiler.py`
- Modify: `habitat/semantic/base.py`
- Modify: `habitat/semantic/project.py`
- Modify: `habitat/storage.py`
- Create: `tests/test_provenance.py`
- Modify: `benchmarks/run_semantic_quality.py`

**Interfaces:**

- Consumes: `BenchmarkCase` and semantic compiler outputs from Task 1.
- Produces: `EvidenceRef`, `ProvenanceEnvelope`, `invalidation_key`, `is_current`, and persisted `provenance_json` fields.

- [ ] **Step 1: Write failing provenance completeness tests.**

```python
def test_every_emitted_symbol_has_revision_bound_provenance(self) -> None:
    ws = self.make_workspace({"app.py": "def run():\n    return 1\n"})
    self.addCleanup(ws.close)
    symbol = ws.search("run")["results"][0]
    provenance = symbol["provenance"]
    self.assertEqual(ws.revision, provenance["revision"])
    self.assertEqual("app.py", provenance["source_path"])
    self.assertTrue(provenance["source_digest"])
    self.assertTrue(provenance["provider"])
    self.assertTrue(provenance["provider_version"])
    self.assertIn(provenance["trust"], {"exact", "provider", "heuristic"})
    self.assertTrue(provenance["invalidation_keys"])
```

- [ ] **Step 2: Run and confirm missing provenance fields.**

Run: `python -m unittest -v tests.test_provenance`

Expected: FAIL because current result objects do not expose the complete envelope.

- [ ] **Step 3: Implement the shared envelope.**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRef:
    kind: str
    ref_id: str
    digest: str | None = None


@dataclass(frozen=True)
class ProvenanceEnvelope:
    revision: str
    source_path: str
    source_digest: str
    provider: str
    provider_version: str
    trust: str
    parse_complete: bool
    evidence: tuple[EvidenceRef, ...]
    invalidation_keys: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "revision": self.revision,
            "source_path": self.source_path,
            "source_digest": self.source_digest,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "trust": self.trust,
            "parse_complete": self.parse_complete,
            "evidence": [item.__dict__ for item in self.evidence],
            "invalidation_keys": list(self.invalidation_keys),
        }
```

- [ ] **Step 4: Persist and migrate provenance.**

Add provenance JSON to symbol, relation, diagnostic, occurrence, effect, and dataflow storage. Use the structural migration system from Truth Core. Legacy rows receive `trust="legacy-unknown"`, `parse_complete=False`, and revision-bound invalidation keys; they are never silently upgraded to exact trust.

- [ ] **Step 5: Implement deterministic invalidation.**

`is_current(envelope, revision, file_digest_lookup)` returns false when the revision differs, source digest differs, provider fingerprint changes, any dependency invalidation key changes, or parse completeness is no longer compatible.

- [ ] **Step 6: Add changed-path tests.**

Cover modify, rename, delete, provider-version change, relation target change, and metadata-preserving edit. Require 100% stale-fact invalidation on the declared cases and no invalidation of unrelated exact facts.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_provenance tests.test_alpha2_semantic_loop`

Run: `python benchmarks/run_semantic_quality.py --split holdout --require-provenance --out .test-artifacts/semantic-provenance.json`

Commit: `git commit -m "feat(semantic): add revision-bound fact provenance"`

## Task 3: Make Project Memory contradiction-aware and self-invalidating

**Files:**

- Create: `habitat/memory_lifecycle.py`
- Modify: `habitat/storage.py`
- Modify: `habitat/workspace.py`
- Modify: `habitat/protocol.py`
- Create: `tests/test_memory_lifecycle.py`
- Modify: `tests/test_alpha11_observatory_runtime.py`

**Interfaces:**

- Consumes: `ProvenanceEnvelope` and `is_current` from Task 2.
- Produces: `MemoryStatus`, `MemoryTransition`, `transition_memory`, `find_contradictions`, and `refresh_memory_statuses`.

- [ ] **Step 1: Write failing lifecycle and non-interference tests.**

```python
def test_source_change_invalidates_memory_instead_of_returning_stale_truth(self) -> None:
    ws = self.make_workspace({"settings.py": "MODE = 'safe'\n"})
    self.addCleanup(ws.close)
    memory = ws.memory_record(
        kind="fact",
        statement="MODE is safe",
        path="settings.py",
    )
    (self.source / "settings.py").write_text("MODE = 'fast'\n", encoding="utf-8")
    ws.refresh("memory-invalidation")
    current = ws.memory(memory["id"])
    self.assertEqual("invalidated", current["status"])
    self.assertEqual(ws.revision, current["invalidated_at_revision"])
```

- [ ] **Step 2: Run and confirm stale active memory remains visible.**

Run: `python -m unittest -v tests.test_memory_lifecycle`

- [ ] **Step 3: Implement the transition machine.**

```python
from enum import Enum


class MemoryStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    CHALLENGED = "challenged"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


ALLOWED_TRANSITIONS = {
    MemoryStatus.CANDIDATE: {MemoryStatus.ACTIVE, MemoryStatus.INVALIDATED},
    MemoryStatus.ACTIVE: {
        MemoryStatus.CHALLENGED,
        MemoryStatus.SUPERSEDED,
        MemoryStatus.INVALIDATED,
        MemoryStatus.EXPIRED,
    },
    MemoryStatus.CHALLENGED: {
        MemoryStatus.ACTIVE,
        MemoryStatus.SUPERSEDED,
        MemoryStatus.INVALIDATED,
    },
    MemoryStatus.SUPERSEDED: set(),
    MemoryStatus.INVALIDATED: set(),
    MemoryStatus.EXPIRED: set(),
}
```

- [ ] **Step 4: Add contradiction identity.**

Normalize memory subjects and scopes without reducing statements to keywords. `find_contradictions` only compares compatible scopes and subjects, records both source IDs and evidence, and moves both active records to `challenged` until an explicit resolution supersedes or invalidates one.

- [ ] **Step 5: Enforce agent privacy.**

Agent-private memory and utility rows require matching `agent_id`. Shared promotion creates a new shared record with promoter identity, evidence, and authority metadata; it does not mutate the private row in place.

- [ ] **Step 6: Add lifecycle coverage.**

Test every allowed and rejected transition, source invalidation, provider change, expiration, contradiction, shared promotion, cross-agent query, deletion/forget, and reopen persistence.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_memory_lifecycle tests.test_alpha11_observatory_runtime`

Commit: `git commit -m "feat(memory): add evidence-bound lifecycle"`

## Task 4: Evaluate context usefulness under strict budgets

**Files:**

- Create: `habitat/context/evaluation.py`
- Create: `benchmarks/corpus/context/discovery/manifest.json`
- Create: `benchmarks/corpus/context/holdout/manifest.json`
- Create: `benchmarks/run_context_quality.py`
- Create: `tests/test_context_evaluation.py`
- Modify: `habitat/context/compiler.py`

**Interfaces:**

- Consumes: provenance-aware facts from Task 2 and active memory from Task 3.
- Produces: `ContextEvaluationCase`, `ContextMetrics`, `evaluate_plan`, and context quality artifacts.

- [ ] **Step 1: Write failing budget and relevance tests.**

```python
def test_context_plan_never_exceeds_authorized_budget(self) -> None:
    case = ContextEvaluationCase(
        case_id="login-validation-001",
        task="fix login validation",
        byte_budget=4096,
        required_objects=frozenset({"symbol:validate_login", "test:test_invalid_password"}),
        forbidden_objects=frozenset({"memory:stale-login-rule"}),
    )
    plan = self.compiler.compile(case.task, budget=case.byte_budget)
    metrics = evaluate_plan(case, plan)
    self.assertLessEqual(metrics.selected_bytes, case.byte_budget)
    self.assertEqual(1.0, metrics.required_recall)
    self.assertEqual(0, metrics.forbidden_selected)
```

- [ ] **Step 2: Run and verify current output lacks evaluation metrics.**

Run: `python -m unittest -v tests.test_context_evaluation`

- [ ] **Step 3: Implement metrics.**

```python
@dataclass(frozen=True)
class ContextEvaluationCase:
    case_id: str
    task: str
    byte_budget: int
    required_objects: frozenset[str]
    forbidden_objects: frozenset[str]


@dataclass(frozen=True)
class ContextMetrics:
    case_id: str
    budget_bytes: int
    budget_compliant: bool
    selected_bytes: int
    authority_bytes_read: int
    required_recall: float
    forbidden_selected: int
    duplicate_bytes: int
    unique_paths: int
    exact_source_ratio: float
    stale_items: int
    latency_ms: float
```

`evaluate_plan` scores required-object recall, forbidden/stale selection, exact-source provenance, path and fact-kind diversity, duplicate bytes, authority reads, selected bytes, and latency.

- [ ] **Step 4: Add corpus scenarios.**

Include bug localization, rename blast radius, configuration change, test selection, CSS/HTML link, database schema investigation, stale memory, contradiction, provider degradation, multi-language relation, and negative-space cases. Holdouts use different identifiers and layouts from discovery fixtures.

- [ ] **Step 5: Enforce hard budget accounting.**

The compiler reserves envelope/metadata bytes before ranking content. It rejects negative budgets, reports truncation explicitly, and never reports a page as exact when source bytes were not read from authority.

- [ ] **Step 6: Verify and commit.**

Run: `python benchmarks/run_context_quality.py --split discovery --out .test-artifacts/context-discovery.json`

Run: `python benchmarks/run_context_quality.py --split holdout --out .test-artifacts/context-holdout.json`

Run: `python -m unittest -v tests.test_context_evaluation`

Commit: `git commit -m "test(context): measure utility under budget"`

## Task 5: Version and compare context ranking policies

**Files:**

- Create: `habitat/context/policy.py`
- Modify: `habitat/context/compiler.py`
- Modify: `habitat/storage.py`
- Create: `benchmarks/compare_context_policies.py`
- Create: `tests/test_context_policy.py`

**Interfaces:**

- Consumes: `ContextEvaluationCase` and `ContextMetrics` from Task 4.
- Produces: `RankingPolicy`, `PolicyComparison`, `compare_policies`, and a versioned policy fingerprint in context receipts.

- [ ] **Step 1: Write failing deterministic-policy tests.**

```python
def test_same_policy_and_revision_produce_same_rank_order(self) -> None:
    policy = RankingPolicy.default()
    first = self.compiler.compile("fix login validation", budget=4096, policy=policy)
    second = self.compiler.compile("fix login validation", budget=4096, policy=policy)
    self.assertEqual(first.object_ids, second.object_ids)
    self.assertEqual(first.policy_fingerprint, second.policy_fingerprint)
```

- [ ] **Step 2: Run and confirm the compiler has no explicit policy contract.**

- [ ] **Step 3: Implement immutable policy configuration.**

```python
@dataclass(frozen=True)
class RankingPolicy:
    version: str
    lexical_weight: float
    graph_weight: float
    memory_weight: float
    exact_source_weight: float
    diversity_weight: float
    stale_penalty: float
    duplicate_penalty: float

    @classmethod
    def default(cls) -> "RankingPolicy":
        return cls("context-v1", 1.0, 0.8, 0.4, 1.0, 0.3, 2.0, 1.0)


@dataclass(frozen=True)
class PolicyComparison:
    pairs: int
    wins: int
    ties: int
    losses: int
    protected_regressions: tuple[str, ...]
    admitted: bool


def compare_policies(
    control: tuple[ContextMetrics, ...],
    candidate: tuple[ContextMetrics, ...],
) -> PolicyComparison:
    control_by_id = {item.case_id: item for item in control}
    candidate_by_id = {item.case_id: item for item in candidate}
    if control_by_id.keys() != candidate_by_id.keys():
        raise ValueError("control and candidate cases are not paired")
    wins = ties = losses = 0
    regressions: list[str] = []
    for case_id in sorted(control_by_id):
        left = control_by_id[case_id]
        right = candidate_by_id[case_id]
        if not right.budget_compliant or right.stale_items > left.stale_items:
            regressions.append(case_id)
        left_score = left.required_recall - left.forbidden_selected
        right_score = right.required_recall - right.forbidden_selected
        if right_score > left_score:
            wins += 1
        elif right_score < left_score:
            losses += 1
        else:
            ties += 1
    return PolicyComparison(
        pairs=len(control_by_id),
        wins=wins,
        ties=ties,
        losses=losses,
        protected_regressions=tuple(regressions),
        admitted=wins > losses and not regressions,
    )
```

- [ ] **Step 4: Preserve frozen control and candidate separation.**

The baseline policy is loaded by immutable version/hash. Candidate parameters live in a separate artifact and cannot overwrite the baseline during a comparison run.

- [ ] **Step 5: Add paired comparison and ablation.**

For each holdout case, run control and candidate against the same revision, task, budget, providers, and cache state. Report per-case wins/ties/losses for required recall, stale selection, exact provenance, bytes, and latency. Ablate graph, memory, feedback, and diversity terms one at a time.

- [ ] **Step 6: Define admission.**

Admit only when the candidate improves required recall or verified downstream outcome, preserves 100% budget/provenance/stale-item gates, has no protected regression, and records all missing pairs. Keyword-density gains alone are rejected.

- [ ] **Step 7: Verify and commit.**

Run: `python benchmarks/compare_context_policies.py --control context-v1 --candidate candidate.json --out .test-artifacts/context-policy-comparison.json`

Run: `python -m unittest -v tests.test_context_policy tests.test_context_evaluation`

Commit: `git commit -m "feat(context): add versioned ranking policies"`

## Task 6: Extract and verify multi-agent coordination semantics

**Files:**

- Create: `habitat/coordination.py`
- Modify: `habitat/workspace.py`
- Modify: `habitat/storage.py`
- Modify: `habitat/protocol.py`
- Create: `tests/test_coordination.py`
- Create: `tests/test_agent_non_interference.py`

**Interfaces:**

- Consumes: atomic transactions from Truth Core and memory privacy from Task 3.
- Produces: `CoordinationService.acquire`, `renew`, `release`, `observe`, `validate_read_set`, `notify`, and `disconnect`.

- [ ] **Step 1: Write failing lost-update, lease-expiry, and privacy tests.**

```python
def test_stale_agent_cannot_commit_after_another_agent_changes_observed_file(self) -> None:
    first = self.ws.agent_open("first")
    second = self.ws.agent_open("second")
    self.ws.agent_observe(first["id"], "app.py")
    self.ws.agent_change(second["id"], "app.py", "VALUE = 2\n")
    with self.assertRaisesRegex(ConflictError, "stale observation"):
        self.ws.agent_change(first["id"], "app.py", "VALUE = 3\n")
```

- [ ] **Step 2: Run and capture any current last-write or scattered-logic failure.**

- [ ] **Step 3: Implement a single coordination service.**

```python
class ConflictError(RuntimeError):
    pass


class CoordinationService:
    def __init__(self, store, clock) -> None:
        self.store = store
        self.clock = clock

    def acquire(self, agent_id: str, resource_kind: str, resource_id: str, ttl_s: int) -> dict:
        if ttl_s < 1 or ttl_s > 300:
            raise ValueError("lease ttl must be between 1 and 300 seconds")
        with self.store.transaction("lease-acquire"):
            return self.store.acquire_lease(
                agent_id, resource_kind, resource_id, self.clock(), ttl_s
            )
```

- [ ] **Step 4: Centralize invariants.**

One active write lease exists per governed resource. Renewal requires the same agent. Expired leases are reclaimed deterministically. Commit validates observed digests and revision. Notifications use a stable cause ID and are idempotent. Disconnect releases leases and retains auditable disconnect evidence.

- [ ] **Step 5: Add schedule exploration.**

Run deterministic interleavings of acquire, observe, modify, renew, expire, commit, acknowledge, and disconnect for two and three agents. Assert no lost update, duplicate notification, cross-agent private-state read, or unreleased expired lease.

- [ ] **Step 6: Verify and commit.**

Run: `python -m unittest -v tests.test_coordination tests.test_agent_non_interference tests.test_alpha9_policy_multiagent_git`

Commit: `git commit -m "refactor(agent): centralize coordination invariants"`

## Task 7: Give Codex agents a compact, truthful session bootstrap

**Files:**

- Create: `habitat/session_bootstrap.py`
- Modify: `habitat/workspace.py`
- Modify: `habitat/mcp_adapter.py`
- Modify: `habitat/protocol.py`
- Modify: `plugins/nolane-habitat/skills/nolane-habitat/SKILL.md`
- Modify: `plugins/nolane-habitat/skills/nolane-habitat-maintainer/SKILL.md`
- Create: `tests/test_session_bootstrap.py`
- Modify: `docs/CODEX-INTEGRATION.md`

**Interfaces:**

- Consumes: database health, provenance, memory lifecycle, context policy, and coordination services from earlier tasks, plus `CapabilityReport` from Security/Operations Task 1.
- Produces: `SessionBootstrap`, `build_bootstrap`, and additive fields in existing orient/inspect responses; no new MCP tool.

- [ ] **Step 1: Write a failing bootstrap-size and truth test.**

```python
def test_bootstrap_is_revision_bound_compact_and_actionable(self) -> None:
    packet = self.ws.orient("repair database migration", budget=8192)
    bootstrap = packet["bootstrap"]
    self.assertEqual(self.ws.revision, bootstrap["revision"])
    self.assertLessEqual(len(json.dumps(bootstrap).encode("utf-8")), 8192)
    self.assertEqual("ok", bootstrap["database_health"]["integrity"])
    self.assertIn("next_safe_actions", bootstrap)
    self.assertNotIn("chain_of_thought", json.dumps(bootstrap).lower())
```

- [ ] **Step 2: Run and confirm the additive bootstrap is absent.**

- [ ] **Step 3: Implement the packet.**

```python
@dataclass(frozen=True)
class SessionBootstrap:
    revision: str
    workspace_identity: dict
    database_health: dict
    capability_report: dict
    active_constraints: tuple[dict, ...]
    relevant_memory: tuple[dict, ...]
    context_policy: str
    coordination_state: dict
    next_safe_actions: tuple[str, ...]
    byte_size: int
```

- [ ] **Step 4: Budget the packet.**

Reserve required identity, revision, health, authority, and safety fields first. Rank optional memory and topology summaries with the current context policy. If truncated, report omitted sections and exact paging actions.

- [ ] **Step 5: Update skills.**

The user-facing skill instructs agents to orient, inspect database/capability health, declare the task, request bounded context, checkpoint before compaction, and verify revision after changes. The maintainer skill adds migration, transaction fault, benchmark, and release gates. Neither skill claims permissions or sandboxing not present in the capability report.

- [ ] **Step 6: Add resume tests.**

Create a session, checkpoint, close, change source externally, reopen, and prove bootstrap reports stale checkpoint/revision instead of restoring stale truth.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_session_bootstrap tests.test_alpha11_observatory_runtime`

Run: `python tools/package.py --check-plugin`

Commit: `git commit -m "feat(codex): add truthful session bootstrap"`

## Task 8: Add Teacher–Student–Judge evolution admission

**Files:**

- Create: `habitat/evolution.py`
- Create: `benchmarks/evolution/manifest.schema.json`
- Create: `tools/run_evolution.py`
- Create: `tests/test_evolution_admission.py`
- Modify: `tools/release_check.py`
- Modify: `plugins/nolane-habitat/skills/nolane-habitat-maintainer/SKILL.md`

**Interfaces:**

- Consumes: semantic/context benchmark artifacts, policy fingerprints, and protected-dimension results from Tasks 1–7.
- Produces: `EvolutionRun`, `PairedTrial`, `AdmissionVerdict`, `admit_candidate`, and a release-lineage manifest.

- [ ] **Step 1: Write failing circular-approval and regression tests.**

```python
def test_candidate_cannot_be_admitted_from_its_own_unpaired_claims(self) -> None:
    run = self.make_run(
        teacher_hash="teacher-a",
        student_hash="student-b",
        judge_hash="judge-c",
        pairs=(),
        candidate_claims=("context is better",),
    )
    verdict = admit_candidate(run)
    self.assertFalse(verdict.admitted)
    self.assertIn("missing paired trials", verdict.reasons)
```

- [ ] **Step 2: Run and verify the evolution module is absent.**

- [ ] **Step 3: Implement immutable run identities.**

```python
@dataclass(frozen=True)
class PairedTrial:
    scenario_id: str
    control_artifact_hash: str
    candidate_artifact_hash: str
    scores: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class EvolutionRun:
    run_id: str
    teacher_hash: str
    student_hash: str
    judge_hash: str
    graph_hash: str
    baseline_failure_ids: tuple[str, ...]
    pairs: tuple[PairedTrial, ...]
    ablations: tuple[PairedTrial, ...]
    protected_dimensions: tuple[str, ...]


@dataclass(frozen=True)
class AdmissionVerdict:
    admitted: bool
    reasons: tuple[str, ...]


def admit_candidate(run: EvolutionRun) -> AdmissionVerdict:
    reasons: list[str] = []
    if run.teacher_hash == run.student_hash:
        reasons.append("teacher and student identities are not isolated")
    if run.student_hash == run.judge_hash:
        reasons.append("student and judge identities are not isolated")
    if run.teacher_hash == run.judge_hash:
        reasons.append("teacher and judge identities are not isolated")
    if not run.baseline_failure_ids:
        reasons.append("control baseline has no observed failure")
    if not run.pairs:
        reasons.append("missing paired trials")
    for pair in run.pairs:
        for dimension in run.protected_dimensions:
            if dimension not in pair.scores:
                reasons.append(
                    f"missing protected score: {pair.scenario_id}:{dimension}"
                )
                continue
            control, candidate = pair.scores[dimension]
            if candidate < control:
                reasons.append(
                    f"protected regression: {pair.scenario_id}:{dimension}"
                )
    return AdmissionVerdict(admitted=not reasons, reasons=tuple(reasons))
```

- [ ] **Step 4: Enforce admission gates.**

Reject when Teacher changes, Student equals Teacher, Judge equals Student, baseline control did not fail, pairs are missing/non-comparable, any protected dimension regresses, locks are stale, raw artifacts are absent, selection is biased, or the score rewards lexical stuffing instead of behavior.

- [ ] **Step 5: Add pressure and non-use controls.**

Include misuse, trigger collision, non-use, stale context, authorization ambiguity, cleanup failure, benchmark leakage, and recovery scenarios. Run Student-on and Student-off ablations.

- [ ] **Step 6: Add saturation.**

Stop an evolution lineage after two consecutive cycles add no failure class or measurable information. Record rejected candidates and unchanged protected dimensions.

- [ ] **Step 7: Integrate release evidence.**

`tools/release_check.py` validates lineage hashes and admits skill/policy artifacts only when `AdmissionVerdict.admitted` is true. Product releases may proceed without a new skill candidate, but may not silently package an unadmitted candidate.

- [ ] **Step 8: Verify and commit.**

Run: `python -m unittest -v tests.test_evolution_admission`

Run: `python tools/run_evolution.py --manifest benchmarks/evolution/control-v1.json --out .test-artifacts/evolution.json`

Commit: `git commit -m "feat(evolution): add independent admission gates"`

---

## Final verification

- [ ] Run `python -m unittest -v tests.test_semantic_benchmark tests.test_provenance tests.test_memory_lifecycle`.
- [ ] Run `python -m unittest -v tests.test_context_evaluation tests.test_context_policy`.
- [ ] Run `python -m unittest -v tests.test_coordination tests.test_agent_non_interference tests.test_session_bootstrap`.
- [ ] Run `python -m unittest -v tests.test_evolution_admission`.
- [ ] Run discovery and holdout semantic benchmarks and verify all thresholds.
- [ ] Run discovery and holdout context benchmarks and verify 100% budget/provenance/stale-item gates.
- [ ] Run the full Habitat test matrix on Windows and Ubuntu.
- [ ] Verify all new response fields are additive and existing protocol/MCP contract snapshots are unchanged.
- [ ] Verify packaged skills reference only existing tools and truthful capabilities.
- [ ] Verify no evolution artifact is admitted with a protected regression or missing pair.

## Completion definition

This plan is complete when Habitat beats or matches the frozen baseline on sealed semantic and context holdouts, every emitted fact and context page has current provenance, memory and agents pass non-interference tests, session bootstrap is compact and truthful, and evolution admission rejects circular or safety-regressing candidates.

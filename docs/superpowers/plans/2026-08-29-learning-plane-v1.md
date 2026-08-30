# Learning Plane V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, evidence-gated Learning Plane that versions bounded context policies, records outcomes, independently evaluates candidates, promotes improved policies, consumes them in Context Compiler, and exactly rolls them back.

**Architecture:** Add a small immutable domain package under `habitat/learning_plane`, persist it through the existing `LearningRepository` and single SQLite Store, expose lifecycle behavior through a lazy `LearningService`, then connect only the promoted context policy to `ContextCompiler`. Authorization/security `PolicyEngine` remains constitutional and unreachable from learning mutations.

**Tech Stack:** Python stdlib, frozen dataclasses, SQLite, existing Habitat Store/Workspace/services, existing Benchmark Lab evidence primitives, unittest.

**Spec:** `docs/superpowers/specs/2026-08-29-learning-plane-v1-design.md`

## Global Constraints

- Preserve alpha.19 public protocol/MCP/workspace behavior unless an explicitly promoted context policy is active.
- Keep one SQLite authority; no second database or service process.
- Learning Plane may never modify source-authority precedence, path escape checks, revision freshness, mutation journaling/recovery, approvals, containment truthfulness, secret-redaction boundaries, stable release review requirements, or authority-class ordering.
- Candidate generator and evaluator identities must be separable; self-report alone can never promote.
- Missing measurements remain `None`; explicit zero remains measured zero.
- Every state-changing multi-row lifecycle operation is atomic.
- RED must be observed before production implementation for each behavior-changing task.
- Final merge requires exact-head CI/CodeQL/review/thread/boundary/main-drift verification.

---

### Task 1: Immutable Context Policy and Constitutional Domain Kernel

**Files:**
- Create: `habitat/learning_plane/__init__.py`
- Create: `habitat/learning_plane/model.py`
- Create: `tests/test_learning_plane_model.py`

**Interfaces:**
- Produces: `ContextPolicy`, `PolicyCandidate`, `EvaluationPacket`, `OutcomeRecord`, `CONSTITUTIONAL_LEARNING_TARGETS`, `LEGAL_CANDIDATE_TRANSITIONS`.
- Consumes: no persistence/runtime state.

- [ ] **Step 1: Write RED tests for ContextPolicy validation and deterministic fingerprint**

Tests require a frozen value with exactly:

```python
ContextPolicy(
    version="context-v1",
    lexical_weight=1.0,
    structural_weight=1.0,
    evidence_weight=1.0,
    graph_depth=2,
    max_roots=8,
    source_prefetch_budget=18,
    abstention_threshold=0.28,
)
```

Require stable SHA-256 fingerprint; version non-empty; finite non-negative weights; `graph_depth in [0, 8]`; `max_roots in [1, 64]`; `source_prefetch_budget in [1, 200]`; `abstention_threshold in [0, 1]`; booleans rejected as numbers/integers.

- [ ] **Step 2: Write RED tests for constitutional target closure**

Require exact set:

```python
{
    "source_authority_precedence",
    "path_escape_checks",
    "revision_freshness_requirements",
    "mutation_journaling_recovery_rules",
    "approval_requirements",
    "containment_truthfulness_rules",
    "secret_redaction_boundaries",
    "stable_release_review_requirements",
    "authority_class_ordering",
}
```

Require `ContextPolicy.from_mapping()` to reject any unknown field, and specifically reject every constitutional name rather than silently ignoring it.

- [ ] **Step 3: Write RED tests for lifecycle/evidence records**

`PolicyCandidate` must bind candidate id, candidate/baseline version+fingerprint, generator id, state, timestamps. Legal states are `candidate`, `shadow`, `experiment`, `evaluated`, `canary`, `promoted`, `rejected`, `rolled_back`.

`LEGAL_CANDIDATE_TRANSITIONS` must be exactly:

```python
{
    "candidate": frozenset({"shadow", "rejected"}),
    "shadow": frozenset({"experiment", "rejected"}),
    "experiment": frozenset({"evaluated", "rejected"}),
    "evaluated": frozenset({"canary", "rejected"}),
    "canary": frozenset({"promoted", "rejected"}),
    "promoted": frozenset({"rolled_back"}),
    "rejected": frozenset(),
    "rolled_back": frozenset(),
}
```

`EvaluationPacket` must bind candidate/policy fingerprint, evaluator identity, held-out suite id, baseline/candidate benchmark fingerprints, independent `improved` verdict, immutable evidence refs, reproduction tolerance. Reject evaluator/generator identity equality when `require_independent(generator_id)` is called.

`OutcomeRecord` must preserve exact task/revision/provider/context/action/verification/outcome/resource/error/rollback bindings as immutable tuples/maps with missing metrics untouched.

- [ ] **Step 4: Observe RED on the exact test commit**

Run full regression. Expected new failure: import/module contract absent; no unrelated legacy failures.

- [ ] **Step 5: Implement minimal frozen domain objects**

Use canonical JSON:

```python
json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
```

and SHA-256 for policy fingerprints. Do not import `habitat.policy.PolicyEngine`.

- [ ] **Step 6: Verify GREEN and commit**

Run focused model tests, then full regression. Commit only when both are green.

---

### Task 2: Additive SQLite Persistence and LearningRepository Contracts

**Files:**
- Modify: `habitat/storage.py`
- Modify: `habitat/storage_migrations.py`
- Modify: `habitat/repositories/learning.py`
- Create: `tests/test_learning_plane_repository.py`
- Extend migration tests only where required by current migration-test pattern.

**Interfaces:**
- Consumes: Task 1 domain values.
- Produces repository methods:

```python
create_policy_version(policy, *, parent_version, created_by, created_at) -> None
policy_version(version: str) -> sqlite3.Row | None
policy_versions(limit: int = 200) -> list[sqlite3.Row]
create_candidate(candidate: PolicyCandidate) -> None
candidate(candidate_id: str) -> sqlite3.Row | None
update_candidate_state(candidate_id: str, expected_state: str, new_state: str, updated_at: str) -> None
append_outcome(candidate_id: str, outcome: OutcomeRecord) -> int
outcomes(candidate_id: str, limit: int = 500) -> list[sqlite3.Row]
append_evaluation(candidate_id: str, packet: EvaluationPacket, created_at: str) -> int
latest_evaluation(candidate_id: str) -> sqlite3.Row | None
append_activation(... exact activation bindings ...) -> int
active_context_policy_version() -> str | None
set_active_context_policy_version(version: str | None, updated_at: str) -> None
```

- [ ] **Step 1: RED schema/repository tests**

Require fresh Store tables:
`learning_policy_versions`, `learning_candidates`, `learning_outcomes`, `learning_evaluations`, `learning_activations`, `learning_state`.

Require policy version immutability: inserting same version with different fingerprint/value must fail; repository updates do not overwrite policy JSON.

Require candidate optimistic state update to fail if stored state != expected state.

Require outcome/evaluation/activation rows append-only and deterministically ordered.

- [ ] **Step 2: RED migration compatibility test**

Open a schema-v22 workspace fixture through the new build. Require pre-migration backup, preservation of legacy rows, creation of Learning Plane tables, and updated schema marker. Future schema remains fail-closed.

- [ ] **Step 3: Observe RED**

Expected failures are missing tables/repository methods/schema version only.

- [ ] **Step 4: GREEN additive schema**

Increment `SCHEMA_VERSION` by one. Add new tables to `storage.py`. Update migration required/additive structure narrowly enough that old workspaces receive the new tables without destructive rebuild.

- [ ] **Step 5: GREEN repository methods**

Persistence only: canonical JSON in/out, exact identities, atomic-compatible methods. Do not place lifecycle authorization logic in repository code.

- [ ] **Step 6: Verify focused migration/repository + full regression and commit**

---

### Task 3: LearningService Lifecycle, Independent Gates, Promotion and Exact Rollback

**Files:**
- Create: `habitat/services/learning.py`
- Modify: `habitat/services/__init__.py`
- Modify: `habitat/workspace.py`
- Create: `tests/test_learning_service.py`

**Interfaces:**
- Consumes Task 1 model + Task 2 repository.
- Produces lazy workspace-owned `LearningService` and methods:

```python
register_context_policy(policy: ContextPolicy, *, parent_version: str | None, created_by: str) -> dict
create_policy_candidate(policy_version: str, *, baseline_version: str, generator_id: str) -> dict
record_policy_outcome(candidate_id: str, outcome: OutcomeRecord) -> dict
transition_candidate(candidate_id: str, target_state: str) -> dict
admit_evaluation(candidate_id: str, packet: EvaluationPacket) -> dict
promote_candidate(candidate_id: str) -> dict
rollback_candidate(candidate_id: str, reproduction: EvaluationPacket) -> dict
active_context_policy() -> ContextPolicy | None
```

- [ ] **Step 1: RED lifecycle transition tests**

Require exact legal state graph, terminal states, optimistic expected-state transition, and no skipped states.

- [ ] **Step 2: RED independent evaluation tests**

`admit_evaluation` rejects wrong candidate/policy fingerprint and evaluator == generator. `transition_candidate(..., "canary")` requires an admitted latest independent evaluation. `promote_candidate` requires current `canary` state and `improved=True`.

- [ ] **Step 3: RED atomic promotion tests**

Promotion atomically records:
- candidate -> promoted;
- previous active policy version/fingerprint;
- new active policy version/fingerprint;
- exact evaluation id/benchmark fingerprints;
- active state pointer.

Inject a failure between writes and prove no partial promotion survives.

- [ ] **Step 4: RED rollback tests**

Rollback only from `promoted`. Reproduction packet must bind the exact previously active policy fingerprint and benchmark fingerprint recorded at activation. Reject outside declared tolerance. Successful rollback atomically restores exact previous version, appends rollback activation, and moves candidate to `rolled_back`.

- [ ] **Step 5: GREEN service + lazy workspace seam**

Follow existing `IndexService`/`RuntimeService` lazy ownership pattern. No protocol methods are added in this task.

- [ ] **Step 6: Verify focused service/fault tests + full regression and commit**

---

### Task 4: Runtime Consumption in ContextCompiler Without Authority Drift

**Files:**
- Modify: `habitat/context/compiler.py`
- Modify: `habitat/workspace.py` only if the existing context compile call requires the active policy to be threaded through.
- Create: `tests/test_learning_context_policy_runtime.py`

**Interfaces:**
- Consumes: `LearningService.active_context_policy()`.
- Produces policy-aware context compilation where policy metadata is recorded in context artifacts.

- [ ] **Step 1: RED default-compatibility test**

Create identical indexed workspace twice: one with no active Learning Plane policy and one using current code baseline. Require same selected object ids/order, decision packet authority warnings, budget behavior, and context trust semantics.

- [ ] **Step 2: RED bounded-control tests**

With an active policy require:
- graph expansion uses `min(policy.graph_depth, hard_cap)` and `min(policy.max_roots, hard_cap)`;
- lexical lane existing candidates get bounded `lexical_weight` multiplier;
- structural/graph lane existing candidates get bounded `structural_weight` multiplier;
- evidence/diagnostic lane existing candidates get bounded `evidence_weight` multiplier;
- no weight can create a candidate absent from existing evidence lanes;
- trust caps and exact-source-before-mutation warnings remain unchanged;
- `source_prefetch_budget` may lower effective selection budget but never raise caller budget;
- abstention threshold may only make abstention more conservative than the existing lower safety floor.

- [ ] **Step 3: RED causal receipt test**

Every compiled context slice/decision packet under an active policy contains exact `learning_policy_version` and `learning_policy_fingerprint`. No active policy emits both as `None`/absent in a backward-compatible manner locked by tests.

- [ ] **Step 4: Observe RED and implement minimal policy threading**

Keep hard safety constants in code; learnable values are bounded inputs, not replacements for authority rules.

- [ ] **Step 5: Verify focused context tests + existing context/compiler suite + full regression and commit**

---

### Task 5: Held-Out Improvement, Promotion/Rollback Proof and Wave 5 Certification

**Files:**
- Create: `tests/test_learning_plane_heldout_promotion.py`
- Create/update only minimal benchmark fixture/evidence helpers if required; do not invent model-quality numbers.
- Update plan/PR metadata only after code head is otherwise final.

**Interfaces:**
- Consumes Wave 4 Benchmark Lab evidence + Tasks 1-4.
- Produces machine evidence for Foundation Convergence exit criteria 8, 9, and 11.

- [ ] **Step 1: RED deterministic held-out context-policy experiment**

Use a frozen synthetic retrieval scenario with the same task/source snapshot for baseline and candidate. Independent evaluator computes success from observable selected context, not candidate self-report. Produce exact baseline/candidate benchmark fingerprints and evidence refs.

Require candidate improvement to be causal to a bounded context-policy parameter and not an authority bypass.

- [ ] **Step 2: RED promotion proof**

Drive one candidate through all lifecycle states with independent held-out evidence, promote it, compile context, and prove the promoted version/fingerprint is the runtime policy receipt.

- [ ] **Step 3: RED rollback reproduction proof**

Rollback with an independent reproduction packet and prove exact previous policy version/fingerprint is active and its benchmark fingerprint is reproduced within declared tolerance. Tampered/out-of-tolerance reproduction must fail closed.

- [ ] **Step 4: RED constitutional audit**

Machine-test that Learning Plane public/domain/service fields cannot name or patch any `CONSTITUTIONAL_LEARNING_TARGETS`, and that authorization `policy.json` remains byte-identical through candidate creation/evaluation/promotion/rollback.

- [ ] **Step 5: GREEN any certification-only gaps**

Only implement defects exposed by the closure tests. Do not weaken gates or add superiority claims.

- [ ] **Step 6: Exact-final-head certification**

Require:
- Ubuntu/Windows × Python 3.10/3.14 Habitat CI success;
- CodeQL Python + JavaScript/TypeScript success;
- full regression and legacy protocol/MCP compatibility;
- migration/recovery/fault-injection success;
- reproducible artifacts/distribution/Semgrep success;
- no unresolved review threads;
- changed-file boundary audit;
- immediate `main` drift check;
- merge with exact expected head SHA;
- verify `main` equals returned merge SHA.

**Claim boundary:** Wave 5 proves a bounded soft context policy can be independently evaluated, promoted, consumed, and exactly rolled back. It does not prove broad autonomous self-improvement, model-weight learning, or general AGI capability.

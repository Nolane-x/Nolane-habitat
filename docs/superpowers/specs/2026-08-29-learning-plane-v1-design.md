# Learning Plane V1 Design

**Status:** implementation design for Foundation Convergence Wave 5

**Source requirements:** `docs/design/FOUNDATION-CONVERGENCE.md` §8 and exit criteria 8, 9, and 11.

## Goal

Turn Habitat's existing bounded context-utility feedback into a real, evidence-gated Learning Plane that can version a small set of non-constitutional context policies, record revision-bound outcomes, move candidates through an explicit lifecycle, promote only after independent held-out evaluation, and roll back exactly to the prior policy when reproduction evidence is acceptable.

This wave must create working behavior, not a metadata-only lifecycle. A promoted context policy must be consumable by the Context Compiler while the absence of an active learned policy preserves alpha.19 behavior exactly.

## Existing seams

- `habitat/repositories/learning.py` already owns context feedback, context utility, epistemic items, and project memory. It remains the single learning persistence repository and will gain policy/outcome/lifecycle methods.
- `habitat/storage.py` already owns one SQLite database and lazy repository facades. Learning Plane tables remain in that database; no second store is introduced.
- `habitat/workspace.py` already uses lazy services for bounded domain extraction. Wave 5 adds `LearningService` using the same pattern.
- `habitat/context/compiler.py` contains the live context selection behavior and hard-coded graph/root/utility/abstention choices. It is the runtime consumption point for a promoted context policy.
- `habitat/policy.py` is the authorization/security `PolicyEngine`. It is constitutional and is explicitly **not** a Learning Plane target. No learning API may patch `policy.json`, source authority, approval rules, containment truthfulness, or related invariants.
- Wave 4 Benchmark Lab provides deterministic held-out suites, independent evaluators, immutable experiment plans, receipts, and pair-level evidence. Wave 5 consumes benchmark fingerprints/evidence references; it must not weaken Benchmark Lab admission semantics.

## Architecture

### 1. Immutable soft policy domain

Create `habitat/learning_plane/model.py` with a frozen `ContextPolicy` matching the Foundation Convergence policy genome:

```python
@dataclass(frozen=True)
class ContextPolicy:
    version: str
    lexical_weight: float
    structural_weight: float
    evidence_weight: float
    graph_depth: int
    max_roots: int
    source_prefetch_budget: int
    abstention_threshold: float
```

The object has deterministic canonical JSON and SHA-256 fingerprint semantics. Numeric values must be finite; weights and abstention threshold are bounded; integer budgets/depths reject booleans and unsafe ranges. A version is immutable and content-addressable by fingerprint.

The first runtime policy intentionally controls only context-orientation behavior. It does not control authorization, authority ordering, mutation safety, revision freshness, approval, containment, redaction, or release review.

### 2. Constitutional boundary

Expose a machine-readable `CONSTITUTIONAL_LEARNING_TARGETS` set containing the forbidden targets from the master plan:

- `source_authority_precedence`
- `path_escape_checks`
- `revision_freshness_requirements`
- `mutation_journaling_recovery_rules`
- `approval_requirements`
- `containment_truthfulness_rules`
- `secret_redaction_boundaries`
- `stable_release_review_requirements`
- `authority_class_ordering`

Learning APIs accept only typed `ContextPolicy`; there is no generic config patch interface. Any serialized/candidate input containing unknown or constitutional target keys fails closed. The authorization `PolicyEngine.update()` surface is never called from Learning Plane code.

### 3. Candidate lifecycle

Create frozen domain records for candidate identity and evaluation evidence. Legal lifecycle:

```text
candidate -> shadow -> experiment -> evaluated -> canary -> promoted
    |          |           |           |          |
    +----------+-----------+-----------+----------+-> rejected
promoted -> rolled_back
```

No reverse transitions exist. `rejected` and `rolled_back` are terminal.

Each candidate binds:
- candidate id;
- candidate policy version/fingerprint;
- exact baseline policy version/fingerprint;
- generator identity;
- lifecycle state;
- creation/update timestamps.

Evaluation evidence binds:
- candidate id and policy fingerprint;
- independent evaluator identity;
- held-out suite identity;
- exact baseline benchmark fingerprint;
- exact candidate benchmark fingerprint;
- explicit independent `improved: bool` verdict;
- evidence references;
- optional declared reproduction tolerance.

Evaluator identity must differ from candidate generator identity before `evaluated`, `canary`, or `promoted` gates can succeed. Agent/candidate self-report is data only and cannot promote.

### 4. Outcome ledger

Persist immutable outcome rows containing the master-plan bindings:
- candidate/policy version;
- task fingerprint and benchmark class;
- provider fingerprints;
- admitted context object/page references;
- action references and verification receipts;
- independent final outcome;
- resource metrics;
- errors and rollback references;
- source/workspace revision;
- created timestamp.

Collections are canonical immutable tuples at the domain boundary and JSON in SQLite. Missing resource measurements remain missing rather than becoming zero.

### 5. Persistence

Extend the existing single SQLite schema and `LearningRepository` with focused tables:

- `learning_policy_versions` — immutable policy JSON + fingerprint + parent version + creator + timestamp;
- `learning_candidates` — candidate/baseline bindings + generator + lifecycle state;
- `learning_outcomes` — append-only outcome ledger;
- `learning_evaluations` — append-only independent evaluation packets;
- `learning_activations` — append-only promotion/rollback activation ledger, including previous active version and benchmark fingerprints;
- `learning_state` — one current active context-policy pointer used only as a projection/cache of activation history.

All multi-row transitions use `Store.atomic()` so lifecycle state, evaluation evidence, and activation state cannot partially commit.

Schema migration remains additive and upgrades existing alpha.19 workspaces without destructive loss. `SCHEMA_VERSION` advances only with migration/backup tests proving existing workspace compatibility.

### 6. LearningService

Add `habitat/services/learning.py` and lazily attach it in `HabitatWorkspace`.

Responsibilities:
- register immutable policy versions;
- create candidates against the exact active/baseline version;
- append outcome evidence;
- transition lifecycle through the legal state machine;
- admit independent evaluation packets;
- canary/promote only when the latest admissible evaluation says `improved=True`;
- expose active context policy;
- rollback a promoted candidate to its exact previous policy only when rollback reproduction evidence binds the expected previous benchmark fingerprint within declared tolerance.

Repository methods remain persistence-only; lifecycle rules live in the service/domain layer.

### 7. Runtime consumption

Modify `ContextCompiler` narrowly. Default behavior with no active Learning Plane policy must be byte/semantic compatible with the current implementation.

When a promoted policy is active:
- `graph_depth` and `max_roots` parameterize graph expansion within existing hard safety caps;
- lexical/structural/evidence weights apply bounded multiplicative adjustments to candidates that already exist. A learned policy cannot create source authority or bypass trust caps;
- `source_prefetch_budget` may further cap the ordinary context selection budget but never raise a caller-provided budget or source-authority limit;
- `abstention_threshold` can make abstention more conservative, but cannot suppress existing exact-source-before-mutation warnings or authority checks.

The policy version/fingerprint is recorded in each compiled context slice and decision packet so outcomes can be causally bound to the policy actually used.

### 8. Held-out improvement and promotion proof

Wave 5 certification must not manufacture model-performance numbers. It will use a deterministic held-out context-policy fixture where a baseline policy and a candidate policy are applied to the same frozen retrieval scenario. An independent evaluator computes a bounded objective outcome from observable selected-context/evidence data and emits exact benchmark fingerprints.

The candidate may be promoted only if this independent held-out packet is admitted and reports improvement. Tests then prove:
1. the active runtime policy becomes the promoted candidate;
2. its fingerprint is present in compiled context evidence;
3. rollback restores the exact previous policy version/fingerprint;
4. a reproduction packet for the restored policy matches the previous benchmark fingerprint within the declared tolerance.

This proves the Learning Plane mechanism and Foundation Convergence exit criteria without claiming general model-quality improvement.

## Failure behavior

Fail closed on:
- unknown/duplicate policy versions or fingerprint mismatch;
- candidate baseline not matching an existing immutable policy;
- illegal lifecycle transition;
- evaluator identity equal to generator identity;
- evaluation packet bound to the wrong candidate/policy/suite/fingerprint;
- promotion without independent improvement evidence;
- rollback without an exact recorded previous activation;
- rollback reproduction fingerprint mismatch outside tolerance;
- any attempted constitutional/unknown learning target;
- non-finite/negative resource metrics where not meaningful.

## Compatibility boundary

- Existing `PolicyEngine`, protocol method names, MCP behavior, workspace APIs, context feedback, project memory, and context compilation behavior remain unchanged unless a promoted Learning Plane context policy is explicitly active.
- Existing databases are upgraded additively with pre-migration backup and structure verification.
- No model-weight training, generic config mutation, hidden chain-of-thought capture, or new database/service process is introduced.
- Observatory remains irrelevant to policy authority.

## Verification

Every implementation task follows observed RED -> minimal GREEN -> full regression. Final merge requires exact-head Ubuntu/Windows × Python 3.10/3.14 CI, CodeQL, protocol/public compatibility, migration/recovery/fault-injection, reproducible artifacts, Semgrep, review/thread audit, changed-file boundary, and immediate main-drift check.
# Nolane Habitat Foundation Convergence — Architecture Specification

**Status:** design proposal for post-0.1.0-alpha.19 convergence work  
**Baseline:** `0.1.0-alpha.19`, commit `5a676f7b542e6b71465047804dfa57e3056988e5`  
**Primary objective:** increase the accuracy, coherence, measurability, and controlled self-improvement capacity of Habitat without rewriting the project or weakening its current source-authority, recovery, policy, and verification guarantees.

---

## 1. Problem statement

Habitat has accumulated a sophisticated cognitive superstructure: Semantic/Effect/Dataflow/Runtime Twins, Context VM, Project Memory, epistemic state, hypotheses and experiments, multi-agent coordination, counterfactual worlds, Executive Trajectory, governed mutation, verification, MCP, and Observatory.

The next bottleneck is not feature count. The system needs stronger convergence between four things:

1. the precision of the project representation;
2. the authority and provenance of claims built from that representation;
3. the measured causal value of each cognitive/action mechanism;
4. the ability to improve soft policies without allowing learned behavior to weaken hard safety/correctness invariants.

The project therefore enters **Foundation Convergence** rather than another feature-accumulation cycle.

---

## 2. Non-negotiable compatibility invariants

The following remain hard constraints throughout convergence:

- Canonical project files remain executable truth.
- A Semantic Twin, memory, summary, runtime inference, or model-produced interpretation never becomes source authority.
- Existing workspace revisions, source anchors, Merkle state, transactions, journals, recovery rules, and mutation conflict checks remain valid.
- Existing public protocol method names remain available during the convergence series.
- The existing 12-tool MCP surface remains compatible unless a later version explicitly deprecates a tool under a versioned migration contract.
- Existing alpha.19 workspaces must open without destructive migration.
- Existing read-only operations must remain logically state-neutral.
- Capability claims remain fail-honest: presence of a binary or configuration is not proof of containment or semantic precision.
- The Observatory remains observer-only and must not acquire mutation authority.
- Private chain-of-thought is neither required nor stored.
- Learning mechanisms may optimize soft policy only; they may not modify constitutional invariants, source authority, approval requirements, containment claims, or release-governance rules.

---

## 3. Target architecture: four planes

### 3.1 Truth Plane

Owns facts whose authority must remain mechanically inspectable.

Responsibilities:

- source authority identity and current materialization;
- revisions, source digests, Merkle roots, exact source anchors;
- observed execution/UI/runtime receipts;
- claim provenance and staleness;
- evidence relationships;
- hard project invariants;
- capability attestations;
- mutation/release authority boundaries.

The Truth Plane answers: **what is known, from what authority, at which revision, and what is allowed to rely on it?**

### 3.2 Cognitive Plane

Owns derived project representations and task-oriented cognition.

Responsibilities:

- Semantic Fabric V2;
- Project World and graph projections;
- Context Compiler and Context VM;
- Effect/Dataflow/Runtime Twin derivations;
- Project Memory;
- epistemic items;
- hypotheses and experiments;
- counterfactual worlds;
- Executive planning inputs.

The Cognitive Plane may derive, rank, summarize, and hypothesize, but never promotes itself to source truth.

### 3.3 Action Plane

Owns operations that can change source or external runtime state.

Responsibilities:

- mutation planning/staging/commit/rollback;
- execution providers;
- browser/UI actions;
- verification actions;
- leases, approvals, mutation authorization;
- agent coordination and invalidation;
- checkpoint/resume action continuity.

The Action Plane must consume explicit authority from the Truth Plane and produce receipts back into it.

### 3.4 Learning Plane

Owns controlled adaptation of soft policies.

Responsibilities:

- outcome ledger;
- causal/ablation experiments;
- policy candidates;
- shadow evaluation;
- canary evaluation;
- independent evaluation;
- promotion gates;
- exact rollback of policy versions;
- benchmark population and held-out task partitions.

The Learning Plane may tune parameters such as retrieval weights, graph expansion depth, context budgets, strategy priors, verifier scheduling, and provider selection. It may not modify constitutional rules.

---

## 4. Constitutional Trust Kernel

Create a small explicit kernel that defines classes of authority rather than allowing every subsystem to interpret `trust` independently.

### 4.1 Authority classes

Initial authority lattice:

1. `SOURCE_EXACT` — exact canonical source bytes or exact immutable source snapshot.
2. `OBSERVED_EXACT` — direct external observation bound to revision/runtime identity, e.g. process exit status or browser semantic observation.
3. `COMPILER_PRECISE` — compiler/LSP/SCIP-derived semantics with provider provenance.
4. `PARSER_DERIVED` — syntax-derived relationship.
5. `HEURISTIC_DERIVED` — deterministic heuristic interpretation.
6. `MODEL_INFERRED` — model-generated claim.
7. `MEMORY_RECALLED` — recalled knowledge retaining the authority/provenance of the original evidence, never gaining authority merely through reuse.

Authority is not a confidence scalar. A high-confidence `MODEL_INFERRED` claim still cannot authorize an operation that requires `SOURCE_EXACT` or `COMPILER_PRECISE` evidence.

### 4.2 Claim record

Introduce a normalized internal representation conceptually equivalent to:

```python
@dataclass(frozen=True)
class Claim:
    id: str
    kind: str
    subject_ref: str | None
    statement: str
    authority: AuthorityClass
    confidence: float | None
    workspace_revision: str
    provider_id: str | None
    provider_version: str | None
    provenance_refs: tuple[str, ...]
    invalidation_refs: tuple[str, ...]
    status: Literal["active", "stale", "contradicted", "superseded", "rejected"]
```

Existing evidence, epistemic items, memory, effect/dataflow facts, runtime evidence, invariant links, and verifier receipts need not be rewritten at once. The first implementation should add an adapter/registry that maps existing records into this authority model.

### 4.3 Authority requirements

Every mutating or promotion operation must declare the minimum evidence/authority it accepts. Example:

```python
OperationPolicy(
    operation="workspace.change.stage_rename_symbol",
    requires=(AuthorityRequirement(kind="rename-sites", minimum="COMPILER_PRECISE"),),
)
```

The aim is to prevent a weak semantic edge from silently acquiring stronger power merely because a higher layer consumed it.

---

## 5. Semantic Fabric V2

Semantic Fabric V2 is the highest-priority capability upgrade.

### 5.1 Provider contract

Create a provider-neutral interface whose implementations can be Python-native, TypeScript-native, Tree-sitter, LSP, SCIP, or future compiler adapters.

```python
class SemanticProvider(Protocol):
    provider_id: str
    provider_version: str

    def probe(self, root: Path) -> ProviderCapability: ...
    def index_file(self, request: FileIndexRequest) -> FileSemanticResult: ...
    def update_file(self, request: IncrementalFileUpdate) -> FileSemanticResult: ...
    def definitions(self, query: SymbolQuery) -> Sequence[SemanticOccurrence]: ...
    def references(self, query: SymbolQuery) -> Sequence[SemanticOccurrence]: ...
    def diagnostics(self, request: ProjectSemanticRequest) -> Sequence[SemanticDiagnostic]: ...
    def rename(self, request: RenameRequest) -> RenameResult: ...
```

A provider may return `unsupported` for capabilities it cannot prove.

### 5.2 Provider registry and arbitration

A `SemanticProviderRegistry` owns:

- discovery;
- capability probing;
- admission;
- provider version/fingerprint;
- precedence per language/capability;
- conflict reporting when precise providers disagree;
- fallbacks.

Default precedence is capability-specific, not global. For example, Jedi may be preferred for Python references while Tree-sitter remains the broad syntax provider.

### 5.3 Tree-sitter baseline

Tree-sitter becomes an actual broad syntax provider, not only a detected capability. It should supply error-tolerant syntax structure, declarations, structural anchors, imports/includes where grammars permit, and incremental parse support.

Tree-sitter-derived relations remain `PARSER_DERIVED` unless corroborated by a stronger provider.

### 5.4 LSP lifecycle manager

Create a workspace-scoped LSP manager with explicit leases/refcounts, deterministic shutdown, request timeout, process identity, and capability negotiation. It must never describe a server as active merely because an executable exists.

### 5.5 SCIP importer

Support existing `.scip` indexes and explicit index generation adapters. SCIP data must preserve original index/tool identity and source revision/fingerprint.

### 5.6 Semantic disagreement

When two admitted precise providers disagree, Habitat must persist/report the disagreement instead of selecting a winner invisibly. Context can rank one result but the contradiction remains observable.

---

## 6. Core convergence without rewrite

### 6.1 `HabitatWorkspace` becomes a compatibility facade

Do not replace it. Gradually move domain logic behind focused services while preserving method signatures.

Target service boundaries:

- `TruthService`
- `SemanticService`
- `ContextService`
- `EvidenceService`
- `MutationService`
- `ExecutionService`
- `CoordinationService`
- `ExecutiveService`
- `LearningService`

`HabitatWorkspace` owns lifecycle and delegates.

### 6.2 Storage repositories over one SQLite unit of work

Do not introduce microservices or a second authoritative database.

Split `storage.py` by code responsibility while retaining one SQLite connection/transaction coordinator:

- `storage/core.py` — connection, atomic/savepoints, schema bootstrap, doctor hooks;
- `storage/source_repo.py` — files/revisions/relations/occurrences;
- `storage/evidence_repo.py` — evidence/claims/invariants/epistemic state;
- `storage/context_repo.py` — context slices, residency, feedback, utility;
- `storage/agent_repo.py` — sessions/observations/notifications/leases;
- `storage/executive_repo.py` — trajectories/milestones/events;
- `storage/runtime_repo.py` — runtime/effect/dataflow records;
- `storage/learning_repo.py` — policy candidates/outcomes/experiments.

The public `Store` remains a facade during migration so existing callers and tests remain valid.

### 6.3 Operation Registry

Replace the giant manual protocol dispatch structure incrementally with a registry.

```python
@dataclass(frozen=True)
class OperationDescriptor:
    name: str
    read_only: bool
    side_effect_class: Literal["none", "workspace", "source", "runtime", "external"]
    idempotency: Literal["pure", "idempotent", "non_idempotent"]
    request_schema: type
    handler: Callable[..., Any]
    minimum_authority: tuple[AuthorityRequirement, ...] = ()
```

The registry must preserve existing wire method names exactly. Migration should begin by registering a small subset and comparing registry dispatch against legacy dispatch in tests before deleting legacy branches.

---

## 7. Benchmark Lab

The existing paired A/B harness becomes the foundation of a first-class evaluation subsystem.

### 7.1 Required metrics

At minimum, per task and per arm:

- independent success verdict;
- model identity;
- scaffold identity;
- input/output token count when available;
- tool calls;
- exact-source bytes faulted;
- context precision/recall proxies;
- irrelevant-object admission;
- wall time;
- ingestion cost;
- warm reconcile cost;
- provider calls;
- failed/repeated strategy count;
- verification count;
- mutation rollback/conflict count.

### 7.2 Benchmark classes

Maintain separate suites for:

- retrieval/orientation;
- semantic navigation;
- refactor/rename;
- debugging;
- multi-file implementation;
- test selection;
- runtime diagnosis;
- UI tasks;
- multi-agent invalidation;
- adversarial/authority tests;
- large repository scaling.

### 7.3 Ablation

Every major cognitive subsystem must be individually disable-able in benchmark mode. Required examples:

- no graph expansion;
- no residency prior;
- no memory;
- no runtime evidence;
- no executive strategy switching;
- parser-only semantics;
- precise provider semantics;
- static retrieval weights versus learned policy candidate.

This creates causal evidence instead of relying on aggregate success alone.

---

## 8. Learning Plane V1

### 8.1 Soft policy genome

A policy version is immutable structured data, e.g.:

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

Equivalent versioned policy records can later cover strategy selection, provider arbitration, and verifier scheduling.

### 8.2 Outcome ledger

For each episode record:

- policy version;
- task fingerprint/class;
- provider fingerprints;
- admitted context objects/pages;
- actions and verification receipts;
- independent final outcome;
- resource metrics;
- errors/rollbacks;
- revision bindings.

### 8.3 Candidate lifecycle

A candidate may move only through:

`candidate -> shadow -> experiment -> evaluated -> canary -> promoted`

or to `rejected`/`rolled_back`.

Promotion requires a machine-readable evidence packet. Candidate generation and candidate evaluation must be separable identities; self-report alone cannot promote.

### 8.4 Forbidden learning targets

The Learning Plane may never modify:

- source-authority precedence;
- path escape checks;
- revision freshness requirements;
- mutation journaling/recovery rules;
- approval requirements;
- containment truthfulness rules;
- secret-redaction boundaries;
- stable release review requirements;
- authority-class ordering.

These are constitutional configuration, not optimization parameters.

---

## 9. Execution Fabric

Execution providers must expose an attestation instead of a vague sandbox boolean.

```python
@dataclass(frozen=True)
class ContainmentAttestation:
    provider_id: str
    provider_version: str
    process_isolation: bool
    filesystem_isolation: bool
    network_isolation: bool
    user_isolation: bool
    capability_drop: bool
    resource_limits: bool
    secret_boundary: bool
    probe_receipts: tuple[str, ...]
```

A configured provider only receives the capability labels actually proven by its probes.

Initial provider evolution should build on existing local-process and Bubblewrap behavior rather than replace them.

---

## 10. Observatory role after convergence

The Observatory becomes an explicit projection layer over durable/read-only state.

Split conceptually into:

- **Observability Core:** read models, activity transport, world/operator state reconstruction, privacy-safe frame references;
- **Cinematic Frontend:** visual layout, animation, camera, operator presentation.

No convergence milestone is allowed to claim architectural progress purely because the cinematic frontend gained features. Frontier work resumes only after semantic and benchmark gates are healthy.

---

## 11. Repository self-consistency gate

Add a machine-readable release-document consistency verifier.

The verifier must check at least:

- `VERSION`;
- `habitat.__version__`;
- `pyproject.toml` package version;
- latest changelog heading;
- README current-version claim;
- implementation-status current-version claim;
- limitations current-version claim;
- current architecture/design target links;
- plugin metadata;
- release manifest version and source commit where present.

Broken current-document links must fail the gate.

Documentation history may intentionally mention older releases; the verifier checks only explicitly designated current-version fields/links rather than searching for every old version string.

---

## 12. Migration strategy

### Wave 0 — Truth baseline

No architectural rewrite. Add current-document consistency tests, benchmark/performance baselines, capability snapshots, and repository governance documentation.

### Wave 1 — Semantic Fabric V2

Introduce provider interfaces/registry, Tree-sitter baseline, precise-provider adapters, LSP lifecycle, SCIP importer, and semantic disagreement records behind current Workspace APIs.

### Wave 2 — Truth/Evidence convergence

Introduce authority classes, claim adapters, operation authority declarations, and contradiction/staleness projection without deleting existing evidence tables.

### Wave 3 — Core decomposition

Introduce service facades, Store domain repositories, and Operation Registry while retaining `HabitatWorkspace`, `Store`, and existing protocol compatibility surfaces.

### Wave 4 — Benchmark Lab

Make controlled experiments and ablations first-class and establish held-out benchmark suites.

### Wave 5 — Learning Plane V1

Add immutable policy versions, outcome ledger, candidate lifecycle, shadow/canary evaluation, promotion, and rollback.

### Wave 6 — Execution Fabric

Add provider containment attestations and portable provider adapters.

### Wave 7 — Observatory projection cleanup

Separate observability core from cinematic frontend and measure headless/runtime costs.

---

## 13. Exit criteria for Foundation Convergence

Foundation Convergence is complete only when all of the following are true:

1. Existing alpha.19 public protocol and MCP compatibility tests pass.
2. Existing workspaces migrate/open without destructive loss.
3. Semantic precision is benchmarked across multiple languages/providers instead of described only by capability detection.
4. Every high-impact semantic/evidence object has explicit provenance and authority class.
5. Read-only protocol operations remain state-neutral.
6. Mutation/recovery/fault-injection suites remain green.
7. Major cognitive subsystems have controlled ablation evidence.
8. At least one soft policy is improved by the Learning Plane on held-out tasks and promoted through an independent evaluation gate.
9. Learned policy rollback restores the exact previous policy and reproduces its benchmark fingerprint within declared tolerance.
10. Repository current-version/docs/release identity is machine-consistent.
11. No learning mechanism can edit or override constitutional invariants.
12. Observatory can be disabled without disabling the control/cognition/runtime core.

---

## 14. Explicit non-goals for the convergence series

Do not introduce unless measurements create a demonstrated need:

- a graph database;
- distributed consensus;
- a cloud control plane;
- a microservice rewrite;
- a universal vector database dependency;
- dozens of new MCP micro-tools;
- model-weight training;
- hidden chain-of-thought capture;
- universal theorem proving;
- claims that Habitat turns an arbitrary model into AGI.

---

## 15. Design principle

The convergence series optimizes vertical integrity rather than horizontal feature count:

```text
source
  -> precise semantics
  -> authority-bound evidence
  -> project world/context
  -> control/action
  -> verification
  -> independently evaluated outcome
  -> causal learning
  -> versioned better policy
```

Every arrow must be inspectable, revision-bound where applicable, and benchmarkable. Habitat becomes stronger not because it contains more named cognitive modules, but because its perception, authority, action, evaluation, and adaptation layers agree on what counts as evidence and can prove when a change actually improved agent performance.

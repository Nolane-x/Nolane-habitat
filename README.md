# Nolane Habitat 0.1.0-alpha.17

## Alpha.17 — stability completion, not surface expansion

Alpha.17 deliberately does not add a new subsystem. It deepens existing Browser/AI Operator, Observatory, source mutation and protocol contracts: runtime UI handles are collision-resistant and cannot be spoofed by project markup, console/network buffers are bounded with explicit drop accounting, observer frame state is read atomically, invalid viewport/action values fail early, and browser-context creation is fully inside the cleanup boundary.

The Observatory now reconstructs its operator projection from a dedicated durable UI-event window instead of the generic 80-event visual timeline, resets frame monotonicity on a new stream epoch, uses portable SQLite file URIs, supports true IPv6 loopback binding/URLs, and respects transport-provided UI-stream poll cadence. Source-authority atomic writes now use unique same-directory temporary files so concurrent writers in one process cannot collide.

Alpha.17 keeps the alpha.16 continuous CDP/WebSocket viewport architecture and all prior executive/world-model behavior. The intent is reliability and claim precision, not feature count.

## Alpha.16 — continuous AI viewport + forensic privacy hardening

Alpha.16 upgraded the AI Operator from action-boundary snapshots to an explicitly tiered near-live transport (`cdp-websocket-live` → cooperative CDP → snapshot fallback). It also bound stream state to session/epoch generations, made browser frames ephemeral, scrubbed sensitive DOM/ARIA/URL/console surfaces, denied project-page access to the privileged loopback DevTools port, and drained raw-CDP workers with the shared browser lifecycle. Semantic/runtime assertions remained the correctness oracle; the continuous viewport is a human observer mirror.

## Alpha.15 — AI Operator / live software mirror

```text
AI control plane → ui.runtime.open / act / observe
                         │
                         ├─ semantic handle + target rect + pointer center
                         ├─ secret-aware value preview / redaction
                         └─ authoritative Playwright viewport frame
                                      │
                                      ▼
                         HABITAT OBSERVATORY
                  WORLD  ·  AI OPERATOR  ·  SPLIT
                         │
              synthetic cursor / click pulse / typing trail
              target brackets / action trace / DOM+network telemetry
```

Highlights:

- every UI runtime open/observe/action refreshes a stable observer-only viewport frame from the same Playwright page the AI acts on;
- Observatory serves those frames through a loopback read-only `GET /api/ui-frame` endpoint and never touches Playwright from HTTP worker threads;
- action previews contain semantic handle, role/name, element rectangle, pointer coordinates and viewport geometry so the cinematic cursor lands on the real target rather than a guessed location;
- `fill`/`press` visualization can show what the AI is typing, while password/token/card-like fields are automatically redacted before activity persistence or display;
- `ui.action-started` and `ui.action-completed` carry privacy-filtered receipts including DOM delta counts, network/console counts, layout-diagnostic count and resulting frame sequence;
- Observatory has WORLD / AI OPERATOR / SPLIT views, browser chrome, local URL/session identity, target brackets, cursor trail, click pulse, typing ghost, action timeline and live action telemetry;
- an active UI session auto-focuses the AI Operator view, while humans can locally switch visualization mode without gaining mutation/control authority;
- the operator frame is explicitly a human visual mirror only; Habitat semantic/runtime assertions remain the verification oracle.

**Alpha.15 claim boundary:** the cursor is a deterministic visualization of recorded semantic target geometry, not OS-level mouse capture. The displayed frame comes from the actual Habitat browser session, but animations between receipts are cinematic reconstruction. Pixel appearance is not used to claim semantic correctness, and the Observatory remains read-only.

Alpha.14 is the **AGI-style executive trajectory + semantic completion gate** checkpoint. It preserves alpha.13 resilience while adding a durable, inspectable control loop for long-horizon agent work: hierarchical milestones, explicit postconditions, revision-bound verifier artifacts, tamper-evident trajectory history, structural strategy switching, negative-memory preservation and fail-closed completion.

## Alpha.14 — executive trajectory and completion proof

```text
OBSERVE → UPDATE → DIAGNOSE → RETRIEVE → COMPOSE → DISPATCH
                                                    │
                         ┌──────────────────────────┘
                         ▼
                      VERIFY ── fail/inconclusive ──► RECOVER ──► strategy switch
                         │                                      │
                         └── evidence current + gates clear ────┘
                                      │
                                      ▼
                                    CLOSE
```

Highlights:

- persistent Executive Trajectories with per-event SHA-256 hash chaining and explicit phase/status/revision/provenance;
- enforced control-phase sequencing: clients cannot jump directly from OBSERVE to VERIFY; failed/inconclusive control steps must enter RECOVER and successful verification must pass REFLECT/CONTINUE before successful CLOSE;
- hard executive budgets for steps/failures/strategy switches plus explicit `workspace.executive.stop` for fail/abandon termination instead of silent unbounded continuation;
- hierarchical milestones with dependency DAG checks, postconditions, priority and rollback notes;
- high/critical milestone completion requires a known successful Habitat verifier artifact, and revision-tagged stale artifacts fail closed;
- structured verifier failure overrides a superficially successful process exit code; real execution/verification receipts persist `workspace_revision`, so old receipts fail closed after source changes;
- completion gate validates the complete executive event chain (not a capped prefix) and blocks on trajectory tampering, dependency defects, unsatisfied critical postconditions, stale agent observations, unresolved contradictions, missing critical invariant verifiers and stale verification;
- strategy switching is structural rather than rhetorical: stale state, contradictions, invariant gaps, repeated failure and verification failure map to different recovery families; if the preferred family equals the current one under a real failure, Habitat selects a different fallback family rather than admitting cosmetic recovery;
- failed/inconclusive executive steps are retained as Project Memory failure records instead of being erased from the work history;
- Observatory read model and cinematic graph now expose trajectories, milestones and active strategy without exposing private model chain-of-thought;
- workspace manifest schema 10 advertises `world_model.executive_trajectory=true` while schema 9 workspaces remain validation-compatible.

**Alpha.14 claim boundary:** the Executive Trajectory governs observable Habitat work products and explicit verifier artifacts. It does not inspect hidden chain-of-thought, make heuristic strategy selection equivalent to AGI, or turn one successful test receipt into a proof of universal program correctness.

Alpha.13 is the **micro-depth resilience + truthful cinematic observability** checkpoint. It keeps the alpha.12 Semantic/Effect/Dataflow/Runtime/Project/Counterfactual world stack, but attacks long-lived failure modes that can leave an agent running while silently misunderstanding its world: replay ambiguity, stale counterfactual verification, memory echo, context thrash, telemetry secret leakage, observer reconnect gaps, runtime provenance collisions, bounded-view deception, per-agent loop/stale state, and schema drift.

## Alpha.13 — micro-depth resilience

```text
AI agent → Habitat world → action/evidence/memory/runtime
                 │
                 ├─ fail-closed state/provenance invariants
                 ├─ loop / thrash / epistemic health
                 ├─ resumable activity nervous system
                 └─ adaptive focus+context observer projection
                                  │
                                  ▼
                       CINEMATIC OBSERVATORY v2
                       human spectator only
```

Highlights:

- append-only Runtime Twin event persistence; duplicate IDs are idempotent only when full durable provenance agrees;
- DAP replay identity via explicit session+sequence when available, with honest `replay_identity=unavailable` fallback when it is not;
- telemetry hygiene before persistence/UI: bounded values plus key-, value- and structural secret redaction for OTel/DAP payloads;
- counterfactual verification generation: an overlay edit makes prior verification stale, failed worlds cannot be promoted, and only fresh passed verification carries admitted support;
- memory-echo suppression within the same revision/scope while preserving the same statement as new historical memory after a source revision;
- context efficiency exposes duplicate page faults, refetch ratio and authority-I/O amplification instead of treating model-visible bytes as backend I/O;
- cognitive loop detector and weighted epistemic pressure over visible Habitat operations/unknowns/contradictions/stale observations/invariant verifier gaps, without inspecting private chain-of-thought;
- `workspace.world.health` plus per-agent Observatory health for pending invalidation, loop risk, leases and private residency;
- coherent SQLite observer core frames, explicit best-effort filesystem projection boundary, resumable SSE via `Last-Event-ID`, retention-gap signaling and read-only per-request database handles;
- Observatory adaptive LOD instead of silent node truncation: high-value/hot nodes survive, hidden state is clustered/disclosed, camera focus uses hysteresis, trajectories/temporal heat show recent agent movement, and activity DOM rendering is frame-batched;
- Effect/Dataflow facts carry revision-compatible Runtime support (`strong/weak/none`) while explicitly keeping static possibility, observed evidence and causality distinct;
- bounded failed-test names now carry total/truncation metadata and aggregate evidence so omitted failures are never silently treated as absent.

**Alpha.13 claim boundary:** health/loop/pressure are environment-level operational heuristics, not model cognition inspection; Runtime support is correlation, not causal proof; observer LOD is a bounded projection with disclosed omissions; SQLite core-frame consistency does not magically snapshot external filesystem providers; no AGI/model-quality superiority is claimed.

Habitat accepts an ordinary folder, ZIP, or loose project file and compiles it into a persistent semantic workspace for AI agents. Canonical source remains ordinary project bytes that humans and normal toolchains can open/build/run. Habitat is a rebuildable cognition/execution layer above those bytes.

Alpha.11 is the **agent-underlay + realtime cognitive observatory** checkpoint. It keeps Habitat controlled by AI agents while adding a read-only human spectator surface, a monotonic activity nervous system, Runtime Twin ingress, provider-capability Semantic Fabric, explicit epistemic records, provenance-bound Project Memory, and stateless explicit agent handles for MCP clients. The human UI is deliberately not an IDE/terminal/control surface.

## Alpha.11 — agent underlay and Habitat Observatory

```text
Codex / Claude Code / custom agent
             │
       MCP / NDJSON / API
             │
             ▼
       Habitat cognition
Semantic Twin · Context VM · Evidence
Epistemic Runtime · Project Memory
Runtime Twin · Transactions · Policy
             │
             ├──────────────► canonical project
             │
             ▼
      query-only read model
             │
          HTTP + SSE
             │
             ▼
     HABITAT OBSERVATORY
     human spectator only
```

What alpha.11 adds:

- `habitat-agent-server` and the MCP CLI auto-start a loopback-only Observatory by default; browser auto-open can be disabled independently;
- Observatory uses a separate SQLite `mode=ro` / `query_only` read model and rejects all HTTP mutation verbs;
- append-only activity events cover agent, context, memory, hypothesis, experiment, mutation, verification, runtime and coordination transitions;
- realtime black/multicolor world map, agent rail, cognitive state, context/project memory, evidence/runtime panel and activity timeline;
- Observatory surfaces task/hypothesis/evidence/action summaries but intentionally never exposes raw private model chain-of-thought;
- Runtime Twin accepts OpenTelemetry-shaped span/log/metric records plus DAP events and attempts revision/path/symbol linkage;
- Semantic Provider Fabric reports Tree-sitter/LSP/SCIP/native capability availability without pretending discovered providers were used;
- explicit Epistemic Ledger (`fact`, `assumption`, `unknown`, `contradiction`, `constraint`, `prediction`) plus bounded `cognition.next` / unknown-unknown probes;
- Project Memory distinct from Context Residency: semantic/episodic/procedural/failure/decision/experiment memory binds revision, provenance, evidence, supersession and invalidation;
- MCP remains a compact 12-tool surface while `habitat_start_task` mints an explicit `agent_id` for stateless follow-up calls.

Quick observer flow:

```bash
habitat-agent-server ./.habitat
# Observatory URL is printed to stderr; stdout remains NDJSON protocol.
```

MCP (optional dependency):

```bash
pip install "nolane-habitat[mcp]"
habitat-mcp-server ./.habitat
```

Disable only the browser auto-open with `--no-open-observatory`, or disable the observer entirely with `--no-observatory`.

**Alpha.11 claim boundary:** the Observatory is a read-only projection of real Habitat state, not a human control plane. Runtime observations are evidence from observed executions, not complete causal inference. Provider discovery is not provider admission. Project Memory is remembered provenance-bound state, not canonical truth. These affordances can reduce cognitive/navigation friction for an external model; they do not prove that the model has become AGI.

Alpha.10 is the **governed cognitive runtime** checkpoint inherited by alpha.11. It preserves alpha.9 policy/multi-agent foundations while adding fail-closed full-sandbox provider probing, read-set invalidation and selective revalidation, path-scoped optimistic transaction rebase, agent-private residency and belief views, host approval tokens, cognitive-state retention/GC, project invariant registry, deeper Git/lockfile world state, scoped repository guidance discovery, bounded world-summary orientation, and a stricter externally evaluated A/B evidence contract.

## Scope

Habitat remains deliberately limited to a project/workspace. It is not a Windows/Linux/macOS replacement and does not attempt to make the agent operate a human desktop.

```text
folder / ZIP / loose source
          │
          ▼
      source authority
          │
   pluggable ProjectBackend
   ├─ exact read / write
   ├─ reconcile / hydrate
   └─ typed execution
          │
          ▼
 materialized compiler view
          │
          ▼
    Semantic Twin
   ├─ symbols / references / occurrences
   ├─ Python AST + Jedi precision partitions
   ├─ TypeScript Program + dirty traversal partitions
   ├─ diagnostics / test/runtime evidence
   ├─ Merkle revision state
   ├─ calibrated Context Compiler
   ├─ virtual source pages + Residency
   ├─ bounded context-utility prior
   ├─ transactional semantic mutation
   ├─ affected-test verification
   ├─ semantic browser runtime
   └─ work-episode causal ledger
          │
          ▼
         agent
```

The Semantic Twin is **derived**, never canonical source authority.

**Inherited execution-security boundary:** trusted-local execution remains unsandboxed. An optional `network-contained` Linux profile adds user/network namespaces, bounded resources and a scrubbed environment, but it still lacks filesystem confinement and therefore reports `sandboxed=false`. `untrusted` policy refuses this provider. Hostile-repository execution remains a production blocker.

## What alpha.10 adds

- composable execution containment with an optional Bubblewrap provider admitted only after a real namespace/mount launch probe; unavailable hosts fail closed instead of silently downgrading;
- observed read-set invalidation notifications: another agent's commit can invalidate a reader's world assumptions and block its commit until explicit selective revalidation;
- path-scoped optimistic transaction rebase: unrelated revision drift no longer rejects a transaction when every touched path/destination precondition still holds;
- agent-private Context Residency and agent-specific belief annotations over shared hypotheses; shared canonical source/evidence remain workspace truth;
- host-granted, expiring, single-use approval tokens plus path-scoped source approval rules and side-effect-free `workspace.change.plan` preflight;
- cognitive-state retention planning/compaction, POSIX state-permission hardening, private-agent forget semantics, and an explicit `state.security` surface that admits encryption-at-rest is still absent;
- project invariant registry linking behavioral requirements to symbols/tests/evidence/config without pretending linked evidence automatically proves the invariant;
- deeper Git temporal surfaces for branches, worktrees, conflict state, commit impact, churn and symbol provenance;
- lock-aware direct dependency world for supported Python/npm lock formats while retaining an explicit non-transitive claim boundary;
- bounded `workspace.world.summary` plus scoped AGENTS/CLAUDE/CONTRIBUTING/Copilot guidance discovery; guidance is never auto-injected into every task;
- stronger weak-edge trust propagation caps so a derived/heuristic graph edge cannot become high-confidence merely through repeated traversal;
- same-model A/B harness schema 3 with independent evaluator support, diff fingerprints and explicit comparability admission: one observed model ID, one scaffold ID and an evaluator are all required before `strong_evidence_ready=true`;
- project/runtime schemas and adversarial alpha.10 regressions covering coordination, governance, retention, sandbox probing, temporal cognition, private beliefs, invariants and release identity.

**Alpha.10 claim boundary:** a successful Bubblewrap capability probe establishes only that Habitat's configured namespace/mount profile launches on this host; it is not a proof against kernel/runtime vulnerabilities. Agent belief confidence is not a calibrated probability. Project invariants are explicit requirements plus evidence links, not automatically proven formal properties. The A/B harness is evaluation infrastructure, not evidence of Habitat superiority until a real same-model/scaffold experiment with an independent evaluator is run.

## Inherited alpha.9 capabilities


- versioned `PolicyEngine` gates source reads/edits, structural mutation, execution capabilities and external browser access before consequential actions;
- `network-contained` Linux execution profile with user/network namespaces, finite process/file/core limits and secret-like environment scrubbing, while explicitly retaining `filesystem_restricted=false` and `sandboxed=false`;
- agent sessions, per-agent context utility and path leases so attention state is isolated and overlapping consequential mutations fail before transaction persistence;
- transaction ownership: only the owning agent may commit/rollback an agent-bound transaction, and expired leases fail closed;
- Git temporal cognition for status/history/blame/line provenance without treating history as current source truth;
- direct dependency cognition from Python/Node/Maven manifests and lockfile presence, with no claim of transitive resolution;
- correlation-aware hypothesis evidence assessment that groups repeated evidence by source/provider and exposes contradiction without claiming calibrated probability;
- MCP server sessions automatically receive an internal agent namespace, so the existing compact 12-tool surface participates in scoped utility and mutation ownership without tool-catalog growth;
- executable `agent_ab_harness.py` for paired same-model filesystem-vs-Habitat experiments. It contains no model/evaluator and cannot manufacture a superiority result.

Alpha.9 inherits the alpha.8 world-truth, sparse-I/O, WAL/fidelity, ignore-policy, strict protocol and hypothesis/experiment hardening. See `docs/architecture/ALPHA9-ARCHITECTURE.md` and `docs/writing-plans/2026-08-07-habitat-alpha9-governed-multiagent-cognition.md`.

## Inherited alpha.6 capabilities

### 1. Pluggable project backend substrate

`ProjectBackend` now separates Habitat cognition from where source and execution live.

Alpha.6 ships:

- `LocalProjectBackend` — normal folder / managed ZIP source;
- `DirectoryMirrorBackend` — a remote-like contract double where canonical authority and Habitat's compiler mirror are different directories.

The mirror backend exists to prove the architecture. It is **not** a claimed Cloudflare Computer integration.

Agent semantics remain the same across backends: orient, inspect symbols, follow references, mutate transactionally and verify.

### 2. Authority-safe exact source

Exact source access routes through backend authority rather than trusting a compiler mirror:

```text
inspect(symbol, body)
context page fault
Context Residency materialization
mutation preflight
```

all bind to current canonical source/digests. A stale context is rejected before it can silently become current evidence.

### 3. Targeted backend hydration

When exact changed paths are already known (for example from a future remote change feed), `refresh_paths()` no longer requires whole-project source/mirror enumeration.

```text
changed paths = ["src/auth.py"]
          ↓
backend hydrate one path
          ↓
workspace hash/compile one candidate
          ↓
semantic dirty closure
```

Deep refresh still exists as the integrity boundary before consequential mutation.

### 4. Execution provenance

Typed capability and verification receipts now bind:

```text
backend_id
execution_backend
```

A test result is therefore not merely `exit_code=0`; Habitat records where the execution evidence came from.

### 5. Bounded context utility feedback

An agent/controller can report selected context objects as `used` or `unhelpful`:

```text
workspace.context.feedback
```

Utility may slightly re-rank a **candidate already supported by independent evidence**. It cannot create relevance, change a source trust grade, or turn prior agent behavior into source truth.

### 6. Selective next-page planning

```text
workspace.context.plan_next
```

plans not-yet-fetched virtual source pages under page/byte budgets. On low-confidence/no-gold retrieval it returns:

```text
action = abstain-or-broaden-query
source bytes read = 0
```

rather than filling the budget with arbitrary source.

### 7. Causal work episodes

Long-horizon work can be recorded as an append-only workflow chain:

```text
task/context
   ↓
transaction staged
   ↓
transaction committed / revision
   ↓
verification receipt / evidence
   ↓
episode outcome
```

Methods:

```text
workspace.episode.start
workspace.episode.status
workspace.episode.finish
workspace.causality.explain
```

This is workflow provenance, **not** a claim of complete program causality.

### 8. Backend- and episode-bound checkpoint/resume

Checkpoint state now binds backend identity in addition to revision, Merkle root, compiler/provider fingerprint, event cursor and residents. It may also bind an active work episode.

Resume still chooses:

- `direct`;
- `selective-revalidate`;
- `reorient`.

Backend/provider/resident drift forces reorientation instead of trusting a narrative summary.

### 9. Backend equivalence verifier

Alpha.6 includes a fixture that runs the same project under local and directory-mirror backends and checks:

- semantic symbols/relations/occurrences before mutation;
- task context result;
- canonical semantic mutation result;
- post-mutation semantic state;
- passing verification;
- backend-specific execution provenance.

The verifier is intentionally local and does not stand in for a real cloud integration.

## Existing deep capabilities retained

- secure folder / ZIP / loose-file ingestion;
- incremental file compiler cache;
- partitioned Python/Jedi precision semantics;
- TypeScript Compiler API + Program/TypeChecker dirty traversal;
- calibrated retrieval with concept coverage/no-gold abstention;
- virtual context address space, exact page faults and prefetch;
- persistent source-free Context Residency;
- content-addressed Merkle project state/diffs;
- first-class active/resolved runtime/test evidence;
- fail-closed Python/Jedi project-wide semantic rename;
- structured capability execution and affected-test verification;
- semantic DOM/accessibility/runtime UI and assertions;
- watcher/event journal for local source;
- compact optional MCP adapter targeting the 2026-07-28 line;
- NDJSON agent protocol and human/operator CLI.

## Cloudflare Computer relationship

Cloudflare Computer is useful validation of the **authoritative workspace + replaceable execution backend** pattern. Habitat intentionally occupies a different layer:

```text
Cloudflare/local/future computer backend
                ↓
      source + execution substrate
                ↓
           NOLANE HABITAT
 Semantic Twin / Context VM / Evidence
                ↓
               agent
```

Alpha.6 does not ship a Cloudflare adapter. `DirectoryMirrorBackend` is a contract double used to ensure that adding one later does not require redesigning Habitat cognition.

## Agent-native execution model

There is still no generic terminal UI primitive. Agents use typed capabilities and receipts:

```text
action.run
workspace.verification.plan
workspace.verification.run
```

A backend may use a process/container/runtime internally, but terminal text is implementation evidence rather than the primary control model.

## Quick start

Python 3.10+:

```bash
python -m habitat create /path/to/project /path/to/project.habitat
python -m habitat enter /path/to/project.habitat
python -m habitat orient /path/to/project.habitat "fix credential validation" --budget 12
python -m habitat backend-info /path/to/project.habitat
```

A ZIP can replace `/path/to/project`.

For the remote-like backend contract double:

```bash
python -m habitat create /path/to/project /path/to/project.habitat --backend mirror
```

This is for backend development/testing, not production remote storage.

## Trust grades

- `exact` — source/runtime bounded fact;
- `semantic` — provider-resolved fact inside its declared boundary;
- `parser` — syntax observation;
- `derived` — deterministic structural inference;
- `heuristic` — candidate requiring stronger verification.

Context utility is a separate non-authoritative attention signal and never upgrades these grades.

## Evidence in this release

The delivery includes executable harnesses for:

- 152 historical + alpha.8 regression/contract tests, with alpha.8 adversarial coverage for stale perception, sparse I/O, stale feedback, episode side effects, CRLF/mode fidelity, WAL recovery, ignore policy, strict protocol, output capture and hypothesis/experiment cognition;
- a >1 MB source sparse-I/O demo separating agent-visible bytes from authority bytes;
- local vs mirror semantic/backend composition;
- stress ingestion of the supplied Nolane AGI skill ZIP;
- a 202-file / 200-distractor line-budget explorer benchmark with no-gold abstention.

These support deterministic **mechanism/correctness** statements only. Model-visible source bytes, authority bytes and compiler/index bytes are distinct metrics; none is automatically a token count. No same-model coding-agent superiority claim is admitted.

## Important limitations

- local execution is explicitly unsandboxed and unsuitable for hostile repositories without a stronger execution provider;
- browser external network is denied by default, but Chromium sandbox posture depends on the host and may be disabled under root;
- Windows currently uses a deep-content perception fallback because POSIX `ctime` semantics are not portable;
- `refresh()` remains an intentional whole-project deep integrity scrub and therefore O(project); ordinary reconcile/mutation paths are cheaper;
- local WAL recovery is not distributed ACID/2PC;
- retention/encryption/secret governance for all persistent cognitive state is incomplete;
- multi-agent leases, ownership, distributed ordering and semantic merges are incomplete;
- Java semantics remain heuristic and broad language precision is uneven;
- hypothesis confidence is an agent belief annotation, not calibrated probability or a full causal model;
- no real Cloudflare Computer transport/backend and no controlled same-model Habitat-vs-filesystem A/B is claimed.

See `docs/architecture/ALPHA8-ARCHITECTURE.md`, `docs/IMPLEMENTATION-STATUS.md`, `docs/LIMITATIONS.md`, `reports/ALPHA6-AUDIT-DISPOSITION-alpha8.md`, and the alpha.8 writing plan.

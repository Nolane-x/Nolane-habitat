# Alpha.10 Architecture — Governed Cognitive Runtime

## Thesis

Habitat must remain a **cognitive layer over project authority and execution providers**, not become another human-oriented computer abstraction. Alpha.10 therefore spends complexity on world-truth integrity, bounded cognition, governance, coordination and evidence rather than GUI breadth.

```text
Canonical Source Authority                 Execution Provider
          │                                      │
          └────────── ProjectBackend façade ─────┘
                           │
                    materialized view
                           │
                    Semantic Twin
       ┌───────────────────┼────────────────────┐
       │                   │                    │
   World Summary       Context VM          Evidence/Tests
       │                   │                    │
 Guidance metadata     private Residency        │
       │                   │                    │
       └────────────── Agent Cognition ─────────┘
                           │
             hypothesis / private beliefs
                           │
              Work Episode / Invariants
                           │
        Policy → Approval → Lease / Read-set
                           │
                  WAL Transaction
                           │
           targeted verification/evidence
```

## 1. Source and execution remain separate roles

`SourceAuthority` answers canonical-byte questions. `ExecutionProvider` answers runtime questions. `ProjectBackend` remains a compatibility façade, not the conceptual owner of both truths. Receipts bind the executor identity; source operations bind authority identity.

## 2. Sandbox admission is capability-based

`filesystem-contained` uses an optional Bubblewrap provider. Admission requires an actual minimal namespace/mount launch, not merely `which bwrap`. The profile uses user/PID/IPC/UTS/network namespaces, a minimal read-only host runtime view, writable project root and scrubbed environment. The result remains bounded by the caller-defined Bubblewrap policy and kernel/runtime vulnerabilities.

If the profile cannot execute, untrusted execution fails closed. Habitat never silently relabels `network-contained` host execution as a full sandbox.

## 3. Coordination is advisory invalidation plus hard mutation ownership

Hard boundary:
- path lease prevents overlapping consequential mutation;
- transaction ownership prevents another agent committing/rolling it back;
- touched-path/destination digest preconditions remain authoritative.

Cognitive boundary:
- exact source/context reads register an agent read-set;
- another agent's commit emits `source-invalidated` notifications;
- a pending invalidation blocks the reader's commit;
- explicit selective revalidation refreshes the world observation and consumes the notification;
- the agent must still re-judge its dependent plan/hypothesis.

Disjoint revision changes may use path-scoped optimistic rebase when target preconditions remain valid.

## 4. Shared world vs private cognition

Shared:
- canonical source/revisions;
- Semantic Twin;
- evidence;
- hypotheses as named alternatives;
- project invariants and causal provenance.

Private per agent:
- context utility;
- resident working set;
- read observations/notifications;
- hypothesis stance/confidence/rationale;
- leases.

An agent belief is not promoted to source truth or shared evidence merely because it is strongly held.

## 5. Governance

`PolicyEngine` gates source and execution action before side effects. Alpha.10 adds:
- path-scoped approval globs;
- side-effect-free `workspace.change.plan`;
- expiring single-use host approval tokens;
- exact resource/action/agent binding where configured.

Granting approval is deliberately a host control surface, not a general autonomous-agent capability.

## 6. Cognitive-state lifecycle

Retention compaction can bound selected append-only non-authoritative history. Active evidence, revisions, transactions, open episodes and shared project provenance are protected. `agent_forget` deletes closed-agent private cognition while preserving the shared world history.

Alpha.10 hardens POSIX state file permissions but **does not encrypt state at rest**. `workspace.state.security` reports this explicitly.

## 7. Temporal/dependency world

Git cognition now covers:
- status/history/blame;
- symbol temporal provenance/churn;
- branches/worktrees;
- conflict state;
- commit file impact.

Dependency cognition combines direct manifests with supported lock snapshots. It does not claim arbitrary transitive resolution, installed-environment equivalence or external API compatibility.

## 8. Guidance is input, not automatic context

Habitat discovers scoped `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md` and `.github/copilot-instructions.md`. It exposes metadata first and paged source only on explicit read. Guidance is not automatically injected into every task and is not trusted as verified world truth.

## 9. Project invariants

The invariant registry lets the workspace name behavioral requirements and link them to symbols, tests, evidence, configuration or requirements. Link types include verifier/implements/constrains/contradicts.

Habitat **does not automatically prove an invariant** from these links. Status transitions remain explicit, and contradiction is surfaced rather than averaged away.

## 10. Evaluation contract

A/B harness schema 3 records paired runs, Git diff fingerprints, tool/tokens/time accounting and optional independent evaluator results. `strong_evidence_ready` is true only if:
1. every run reports model identity;
2. exactly one model ID is observed;
3. every run reports scaffold identity;
4. exactly one scaffold ID is observed;
5. an independent evaluator is configured.

This is an admission contract, not a superiority result.

## Explicit open boundaries

- No universal production sandbox: Bubblewrap is host/profile dependent; microVM/container backends remain future providers.
- No distributed multi-process consensus/merge protocol.
- No formal proof engine for project invariants.
- No calibrated Bayesian belief probability.
- No complete production/runtime world model outside repository/runtime evidence currently connected.
- No universal Java/Go/Rust/C++/C# semantic parity.
- No real same-model Habitat-vs-filesystem result until external agents/evaluator are supplied.

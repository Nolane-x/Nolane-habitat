# Alpha.9 Architecture — Governed Multi-Agent Cognition

## Charter
Alpha.9 strengthens the boundary between a derived cognitive workspace and consequential world actions. It adds explicit policy decisions, partial Linux containment, agent-scoped attention state with path leases, temporal Git provenance, direct dependency-world cognition, correlation-aware hypothesis evidence assessment, and an executable same-model A/B orchestration contract.

The checkpoint is **not** admitted as a production hostile-code sandbox or distributed multi-agent database.

## 1. Objective world vs agent-specific cognition

Habitat now models a minimum separation:

```text
SHARED OBJECTIVE WORLD
canonical source / revisions / verified evidence / Semantic Twin

AGENT-SCOPED COGNITION
context utility / agent session / owned leases

CONSEQUENTIAL WORLD ACTION
policy gate → lease/ownership gate → transaction → verification
```

Agent-specific utility can alter bounded attention for that agent only. It cannot change trust grades, source facts, another agent's utility, or shared verification evidence.

## 2. Lease-bound mutation ownership

When `agent_id` is present, Habitat acquires per-path leases **before** a transaction is staged. A second agent cannot stage an overlapping path while the lease is live. Commit/rollback requires the transaction owner and rechecks lease validity. Expired leases cause fail-closed commit.

This is optimistic/local coordination. It is not distributed consensus, a CRDT or semantic merge engine.

## 3. Policy service

`policy.json` is an explicit, versioned operator policy. Alpha.9 evaluates:

- source read/edit path admission;
- structural mutations;
- execution capability kind / deny list;
- untrusted-mode sandbox requirement;
- external browser access.

Default policy preserves trusted-development compatibility. Policy decisions are inspectable; approval-required means the autonomous operation is not executed because alpha.9 does not invent a human approval.

## 4. Partial Linux containment

The local provider can be configured as `network-contained` when Linux user+network namespaces are available. It adds:

- user/network namespace isolation;
- finite process/file/core resource limits;
- secret-like environment variable scrubbing;
- existing bounded stdout/stderr capture.

It **does not provide filesystem confinement**. Therefore `sandboxed=false` remains true and `untrusted` policy refuses local execution. Full hostile-code safety remains a blocker.

## 5. Git temporal cognition

Habitat can query the canonical Git worktree for status, history, blame and line explanation. This answers historical provenance questions without treating Git metadata as current source truth. A blame/commit message is evidence about history, not proof that the old rationale is still behaviorally correct.

## 6. Dependency-world cognition

Direct dependency facts are parsed from `pyproject.toml`, `requirements.txt`, `package.json` and Maven `pom.xml`; common lockfile presence is recorded. Alpha.9 does not infer a transitive resolved dependency graph, vulnerabilities or external API compatibility.

## 7. Correlation-aware hypothesis evidence

Hypothesis status contains an `evidence_assessment` that groups linked evidence by source/provider. Repeated receipts from one provider use diminishing returns rather than being counted as independent votes. Contradictory source groups are visible.

The assessment is a heuristic evidence balance, explicitly `calibrated_probability=false`.

## 8. Same-model A/B harness

`benchmarks/agent_ab_harness.py` pairs ordinary-filesystem and Habitat arms across cloned task repositories and repetitions. It contains no model and no evaluator. Evidence is admissible only when both external commands truly use the same model/scaffold/budgets and an independent evaluator determines success.

## Claim boundary
Alpha.9 supports stronger governance, temporal/project context and local multi-agent coordination. It does not establish coding-agent superiority, distributed concurrency safety, full dependency resolution, causal understanding, or a production sandbox.

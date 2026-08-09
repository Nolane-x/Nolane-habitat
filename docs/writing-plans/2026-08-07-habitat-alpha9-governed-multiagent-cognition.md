# Writing Plan — Habitat Alpha.9 Governed Multi-Agent Cognition

## Charter
Advance Habitat without undoing alpha.8 integrity. Consequential actions must become more governed and multi-agent-safe, while cognition gains temporal and dependency context. Do not label partial containment a sandbox and do not fabricate same-model benchmark results.

## Belief ledger

### B1 — Explicit policy is safer than scattered booleans
**Rival:** policy adds ceremony but no enforcement.  
**Probe:** deny a path and stage mutation; set `mode=untrusted` and attempt unsandboxed execution.  
**Postcondition:** both fail before side effects.

### B2 — Local agent leases can eliminate a major overlap race
**Rival:** revision checks alone are sufficient.  
**Probe:** Agent A stages path X, Agent B stages X before A commits.  
**Postcondition:** B is refused before transaction persistence; only owner may commit/rollback.

### B3 — Agent-specific utility must not contaminate other agents
**Probe:** A marks a context object useful; B runs the same task.  
**Postcondition:** only A's ranked candidate carries agent utility prior.

### B4 — Network namespace containment is useful but not a full sandbox
**Probe:** contained child attempts external TCP.  
**Postcondition:** network fails, resource/security receipt reports network restriction, while `filesystem_restricted=false` and `sandboxed=false` remain explicit.

### B5 — Git provenance adds decision-relevant temporal evidence
**Probe:** committed file → history/blame/explain; working tree mutation → dirty status.  
**Postcondition:** canonical Git output is structured without mutating the repo.

### B6 — Evidence from one provider must not become fake consensus
**Probe:** two exact failures from one pytest source support one hypothesis.  
**Postcondition:** independent source group count remains one; support strength gets diminishing return.

### B7 — Same-model A/B must be executable without being simulated
**Probe:** run harness with deterministic external contract-double agents.  
**Postcondition:** both arms/repetitions execute; harness itself never supplies model score/evaluator success.

## Implementation milestones
1. PolicyEngine + policy file + protocol/CLI surfaces.
2. Network-contained local profile + capability probe and honest security posture.
3. Agent session and agent-context utility namespace.
4. SQLite path leases + transaction ownership.
5. Git cognition.
6. Direct dependency cognition.
7. Evidence fusion assessment.
8. MCP server session binds an internal agent namespace without expanding the 12-tool catalog.
9. Same-model A/B orchestration harness.
10. Historical regression + final-artifact admission.

## Admission gates
- all historical tests pass by exhaustive shards;
- alpha.9 adversarial tests pass;
- compileall passes;
- manifest/schema compatibility passes;
- vertical demo proves lease conflict + owner commit + verification + Git/dependency/security outputs;
- supplied AGI ZIP warm/integrity stress does not regress materially;
- final ZIP manifest independently verifies after packaging.

## Explicit non-goals / open blockers
- filesystem-confined hostile-code sandbox;
- distributed leases/consensus/semantic merge;
- transitive dependency solver;
- Git branch/PR merge cognition as a full world model;
- calibrated Bayesian uncertainty;
- actual same-model A/B result without an external model/evaluator.

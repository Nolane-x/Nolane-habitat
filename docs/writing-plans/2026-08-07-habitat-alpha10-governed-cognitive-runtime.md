# Writing Plan — Alpha.10 Governed Cognitive Runtime

## Charter

Evolve alpha.9 without weakening alpha.8/9 integrity. A feature is admitted only if it changes a measurable runtime property or closes a named world-truth/governance gap. Do not claim a capability merely because an interface exists.

## Protected invariants

1. Canonical source bytes remain authority.
2. Derived Semantic Twin is rebuildable and revision-bound.
3. Consequential actions validate policy/ownership/preconditions before side effects.
4. A weak semantic hypothesis cannot become exact evidence by graph repetition.
5. Agent-private memory cannot silently become shared truth.
6. Full-sandbox status is false unless the configured provider actually launches its containment profile.
7. A/B result is not strong evidence without observed same model/scaffold and independent evaluation.

## Major hypotheses and falsifiers

### H1 — Full-sandbox provider should fail closed
Probe: configure `filesystem-contained` on a host without working Bubblewrap.  
Kill criterion: silent fallback to local/network-only execution.

### H2 — Read-set invalidation should reduce stale-plan commits without serializing disjoint work
Probe: A observes B-path, stages A-path; B mutates observed path. A commit must stop until revalidation. A completely unobserved disjoint edit may optimistic-rebase.  
Kill criterion: global revision lock rejects all disjoint work, or stale observation is ignored.

### H3 — Private cognition must be private
Probe: A/B hold opposing beliefs and different resident sets.  
Kill criterion: B inherits A utility/belief/residency without explicit shared evidence.

### H4 — Governance must be visible before staging
Probe: policy plan on approval-scoped path.  
Kill criterion: preflight creates transaction/lease/source mutation.

### H5 — World summary reduces orientation calls without becoming a repository dump
Probe: summary returns bounded state counts/identities and no exact source bodies.  
Kill criterion: whole source/guidance payload is embedded by default.

### H6 — Guidance discovery must not become context pollution
Probe: repository has multiple instruction files.  
Kill criterion: all guidance automatically appears in every task context.

### H7 — Invariant registry must surface contradiction rather than auto-prove
Probe: one verifier link plus one contradiction link.  
Kill criterion: status silently becomes verified.

### H8 — A/B harness must reject unverified comparability
Probe: identical commands without model/scaffold IDs or evaluator.  
Kill criterion: strong evidence flag becomes true.

## Milestones

M1 sandbox capability provider and admission probe.  
M2 read-set/notification/private residency storage.  
M3 selective revalidation + commit gate.  
M4 path-scoped optimistic transaction rebase.  
M5 approvals, policy preflight and host governance.  
M6 retention/permissions/private-agent forgetting.  
M7 Git temporal/dependency lock cognition.  
M8 project invariant registry.  
M9 shared hypothesis/private agent-belief separation.  
M10 world summary + scoped guidance.  
M11 controlled A/B harness v3.  
M12 exhaustive historical regression + supplied AGI stress + clean-package admission.

## Unknown-unknown probes

- full test lifecycle with persistent TS/browser services;
- legacy DB migration into new schema tables;
- Bubblewrap executable present but namespaces denied by host policy;
- agent revalidation notification races;
- create/move destination appearance during optimistic rebase;
- agent forget cascade accidentally deleting shared hypothesis/evidence;
- guidance file ignored by source policy;
- Git repo in detached HEAD/worktree/conflict state;
- package version drift between runtime and wheel metadata.

## Claim boundary

Alpha.10 may claim implemented mechanisms and their regression/fixture evidence. It may not claim production hostile-code safety, formal invariant proof, calibrated intelligence, distributed multi-agent correctness, or coding-agent superiority without the controlled external evaluation.

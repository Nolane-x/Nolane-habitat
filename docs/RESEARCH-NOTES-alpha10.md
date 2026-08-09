# Alpha.10 Research Notes

## Repository context

2026 retrieval work (ContextBench, Agent Retrieval Bench, FastContext) reinforces that repository cognition should optimize not only recall but precision, budgeted context yield, selective abstention and separation of exploration from solving. Habitat therefore keeps explorer/Context VM separation and does not auto-inject discovered repository guidance.

A recent evaluation of repository context files such as AGENTS.md reports that broad static context can increase exploration/inference cost without reliable task-success gains. Alpha.10 treats guidance as scoped, explicit input rather than mandatory solver history.

## Sandboxing

Bubblewrap exposes Linux namespace/mount primitives but explicitly leaves the security policy to its caller. Production coding environments similarly combine OS-level sandboxing with separate network policy and often stronger container/dev-environment boundaries. Alpha.10 consequently uses an executable capability probe and refuses silent downgrade. Bubblewrap remains a provider option, not a universal proof of safety.

## Multi-agent concurrency

Long-running agent trajectories make traditional coarse lock/OCC strategies expensive. Alpha.10 combines hard ownership where side effects occur (leases/transaction ownership) with advisory read-set invalidation so an agent can selectively re-judge assumptions after another trajectory changes observed state. Path-scoped optimistic rebase avoids rejecting unrelated work solely because the global revision advanced.

## Evaluation

Same-model claims require controlling the deployed product configuration, not merely using similar prompt text. Alpha.10 A/B harness therefore requires explicit model/scaffold identity in every run and an independent evaluator before the report can say it is ready for strong evidence.

## Non-conclusions

These research directions motivate architecture. They do not establish that Habitat is faster, safer or more capable than existing coding agents. Those are empirical questions left to controlled evaluation.

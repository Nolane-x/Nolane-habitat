# Research Sources and Design Consequences — alpha.10

This note records external research used to challenge architecture. It is design input, not product evidence.

- **ContextBench (2026)**: process-level context evaluation reports a recall-over-precision tendency and a gap between explored and actually utilized context. Habitat response: preserve explorer/solver separation, page faults, utilization accounting, abstention, and avoid unconditional context injection.
- **FastContext (2026)**: demonstrates a specialized exploration layer returning focused paths/line ranges can improve end-to-end coding-agent outcomes in its reported setup while reducing solver token consumption. Habitat response: `workspace.explore` remains separate from exact-source Context VM exposure.
- **SWE/experience-context work (2026)**: selected/relevant experience can help while unfiltered experience can hurt. Habitat response: private utility/residency is bounded and agent-specific rather than global truth.
- **VS Code agent trust/safety (2026)**: OS-level sandboxing uses platform primitives; Linux/WSL2 uses Bubblewrap and separate network policy, while full environment isolation can require a dev container. Habitat response: sandbox capability is provider/probe based and never silently downgraded.
- **Bubblewrap security guidance**: Bubblewrap is a sandbox construction toolkit; protection depends on caller-defined arguments/policy. Habitat response: `bwrap` presence alone is never a safety claim.
- **Repository guidance-file evaluations (2026)**: broad static instruction context is not guaranteed to improve task success and can add cost. Habitat response: discover guidance as scoped objects, no auto-injection.

No external source above establishes that Habitat is faster, safer, or more capable than another coding agent. Those claims require the controlled A/B contract with real agents and evaluator.

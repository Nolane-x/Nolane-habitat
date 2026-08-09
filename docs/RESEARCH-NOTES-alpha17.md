# Research Notes — alpha.17 stability completion

## Scope lock
Alpha.17 intentionally avoids new subsystems. The pass asks whether the existing Browser/AI Operator, Observatory, protocol, source authority and lifecycle contracts remain truthful under small adversarial edge cases.

## Findings converted into invariants
- Runtime UI identity must not trust project-authored handle attributes or duplicate DOM IDs.
- Observer event queues must be bounded and loss must be reported.
- Frame sequence/path/source must be read atomically across the CDP worker boundary.
- A busy generic activity timeline must not erase the durable active Operator projection.
- Stream generations reset monotonic counters.
- Advertised IPv6 loopback support must bind an IPv6 socket and emit a valid bracketed URL.
- Atomic source writes require unique same-directory temporary files even inside one PID.
- Input validation belongs before browser action semantics and cleanup must cover context/page creation.

These are reliability/completeness rules, not claims of AGI or universal correctness.

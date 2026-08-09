# Self Audit — Nolane Habitat 0.1.0-alpha.14

## Audit method
Alpha.14 was not treated as a feature-count exercise. The supplied Nolane-AGI Cognitive System 4.0 architecture/research/skills were used as a control-architecture checklist: versioned world state, explicit uncertainty/invalidation, hierarchical postconditions, strategy switching under stagnation, negative evidence retention, bounded execution, receipt/read-back verification and independent completion gates.

## Major gap closed
Alpha.13 already had a strong semantic/runtime/project world and resilience diagnostics, but `workspace.cognition.plan` was still a bounded heuristic projection. It did not provide one durable long-horizon object that could prove what phase the work was in, which milestones were satisfied, which verifier established a postcondition, whether evidence was current, why strategy changed, or why closure was allowed.

Alpha.14 adds that missing durable Executive Trajectory layer rather than exposing private model reasoning.

## Defects found and corrected
1. **Static plan instead of durable executive history** — added persistent trajectories, hierarchical milestones and hash-chained events.
2. **Phase skipping was representable** — control sequence is now enforced; failed/inconclusive work routes to RECOVER and successful closure requires VERIFY then REFLECT/CONTINUE.
3. **Budget metadata was not a hard loop guard** — step/failure/strategy-switch meters now fail closed and explicit stop terminates failed/abandoned work without a false success claim.
4. **Cosmetic strategy switching** — repeated failure cannot be admitted as a switch to the same strategy family; a structural fallback is selected.
5. **Failure could disappear from the plan narrative** — failed/inconclusive executive steps are preserved as provenance-bound Project Memory failure records.
6. **Verifier ambiguity** — structured FAILED overrides `exit_code=0`.
7. **Synthetic revision freshness without production provenance** — real run/verify receipts now persist `workspace_revision`; old receipts are rejected after source mutation.
8. **Assurance reused a bounded event projection** — the default assurance chain now reads all events; a regression test tampers beyond event 1,000 and confirms detection.
9. **Completion could be self-declared** — a fail-closed gate now checks chain integrity, phase sequence, postconditions, known successful verifiers, revision freshness, contradictions, coordination invalidations and critical invariant coverage.
10. **Shared Playwright engine leaked beyond the final workspace** — BrowserRuntime now leases the process-shared engine; the last close drains Playwright and joins the HTTP thread.
11. **Manifest compatibility risk during schema bump** — schema 10 requires `executive_trajectory`; schema 9 remains validation-compatible.
12. **Release-state drift** — implementation status/limitations/capability diagnosis had stale alpha.11/alpha.9 identity and are synchronized to alpha.14.
13. **Packaging contamination risk** — delivery packaging now excludes `build/` and `*.egg-info` in addition to cache/`dist` directories; deterministic ZIP date matches alpha.14.

## Deliberate boundaries retained
- No raw/private chain-of-thought capture.
- No claim that deterministic strategy heuristics constitute AGI.
- No claim that one passing receipt proves universal software correctness.
- No silent claim of token/time/compute metering: only step/failure/switch executive budgets are hard-metered.
- MCP remains a compact 12-tool high-level surface; the detailed Executive API is available on the lower protocol surface rather than increasing tool-selection noise.

## Verification
The final source tree was collected as 257 tests and admitted through six independent process shards. Result: **257/257 PASS**, all counted shards exit code 0. Static syntax/schema gates and isolated-wheel smoke also pass. Exploratory runs that did not complete at the host boundary were not counted as success.

# Alpha.6 External Audit Disposition — Alpha.8

This file records how alpha.8 treats the supplied 59-finding audit. The audit was re-probed against alpha.7 first; a historical finding was not assumed to still exist merely because it appeared in the report.

## A. Corrected / materially strengthened in alpha.8

1. **Stale perception on same-size/restored-mtime edits** — POSIX ordinary reconcile now uses size/mtime/ctime/inode candidate fingerprints and targeted content hash; Windows deliberately deep-verifies until a native journal is implemented.
2. **Virtual Context hidden whole-file I/O** — exact source supports sparse authoritative line-range reads; accounting separates model-visible and authority-read bytes.
4. **ASCII-centric task tokenizer** — Unicode-aware tokenization and casefolding; retrieval index supports Unicode identifiers.
5/7. **confidence concept-composition / long-task denominator** — evaluated-term denominator plus coherent multi-concept support; confidence remains explicitly heuristic.
6. **budget=0 inconsistency** — strict `[1,200]` context budget validation.
8. **feedback from stale context / unbounded utility** — stale feedback rejected; utility decay/cap introduced. Full per-agent isolation remains open.
9. **Work Episode loopholes** — stale context cannot start episode; episode is validated before stage/verify; completed episode cannot leave a staged mutation.
10/11. **MCP cognitive loop gap** — start task opens an episode; context-step exposes feedback→plan→fault while catalog remains compact.
12. **CRLF / executable bit destruction** — newline and ordinary file metadata preserved by source write path.
13. **exception-only transaction rollback** — local write-ahead journal and startup recovery added. This is not distributed ACID/2PC.
14. **small mutation vocabulary** — create/delete/move file added as first-class transaction operations.
17. **false unique-name Python call edge** — no cross-file bare-name call edge without binding/import evidence.
22/23. **evidence environment/scope ambiguity** — environment fingerprint added; test failure resolution is capability/path scoped.
25. **output cap after full in-memory capture** — subprocess output is streamed to bounded temporary storage, prefix-capped on admission; total bytes preserved.
26. **wrong host Python environment** — project `.venv`/`venv` discovery added for Python test capabilities. Broader environment managers remain open.
27. **browser unrestricted external network** — external navigation/network denied by default; root-host Chromium may still require `--no-sandbox`, explicitly reported.
29/30. **`.gitignore` absent / hard-ignore overreach** — `.gitignore` + `.habitatignore`; hard ignores narrowed to VCS/cache/control roots.
31. **Habitat indexes its own database** — workspace state inside source tree is rejected.
32/33. **managed single-file/workspace identity contamination** — existing workspace reuse requires explicit reset; managed single-file source is cleared before replacement.
36. **Residency hidden whole-file I/O** — byte estimation uses compiler metadata; exact materialization uses sparse source ranges.
42/43. **retrieval linear scan hotspots** — persistent symbol-term inverted index introduced for common lexical/morphological lookups. Not every graph operation is index-optimal yet.
56. **MCP error-after-side-effect ambiguity** — committed mutations return `COMMITTED_VERIFICATION_ERROR` if verification fails after commit.
57. **protocol coercion** — consequential booleans/integers/floats reject wrong JSON types rather than Python truthiness/coercion.
58. **non-UTF8 called exact text** — decoded text explicitly reports lossy replacement; authoritative bytes/digest remain separate.
53. **missing hypothesis layer** — revision-bound hypothesis/evidence/experiment primitives added with explicit non-calibrated belief semantics.

## B. Already materially improved by alpha.7 / retained

18. **TypeScript whole-project process startup** — alpha.7 introduced a persistent TypeScript LanguageService with dirty source partitions. API-surface changes can still require broader invalidation.
40. **remote targeted path economics** — directory-mirror contract supports known-path targeted hydration without enumeration. Production remote change feeds/ETags remain open.
44. **test lifecycle/process drain** — host runtime service cleanup is first-class and idempotent; release still uses sharded gates when an external runner imposes a wall-clock timeout.

## C. Partially mitigated but deliberately OPEN

3. **retrieval is not deep semantic cognition** — improved indexing/calibration, but Habitat still primarily supplies evidence to model reasoning.
15/19/20. **language precision breadth** — Python strongest, TypeScript strong, Java and other languages incomplete.
16. **dynamic Python semantics** — absence of static edge is not proof of no dependency; dynamic dispatch remains open.
21. **impact analysis breadth** — graph-linked affected tests are not exhaustive program impact proof.
24. **host execution security** — receipts now expose unsandboxed posture, output is bounded/redacted, but OS confinement is not implemented.
28. **UI component cognition** — runtime semantic UI remains incomplete for framework state/dataflow.
34/35. **retention / encryption / sensitive persistent state** — output redaction helps but policy/GC/encryption is not complete.
37/38. **residency inertia / per-agent memory isolation** — bounded utility improves it, but a full objective/shared/agent-belief separation is not complete.
39. **multi-agent concurrency** — revision checks exist; leases, distributed clocks and merge semantics remain open.
41. **O(project) deep scrub** — `refresh()` intentionally remains explicit full cryptographic integrity scrub. Ordinary reconcile and mutation paths are cheaper/targeted.
45. **adversarial test classes** — alpha.8 adds direct regressions for several requested classes; property/fuzz/concurrency/SIGKILL/disk-full/network-partition scale suites remain open.
47. **accounting denominator** — model-visible and authority I/O separated; provider-internal total rescan accounting is still incomplete.
48/49/50. **Git/dependency/production world cognition** — open.
51. **formal autonomous policy layer** — source/execution posture is explicit but fine-grained authorization/approval/risk budgets remain open.
52. **uncertainty calculus** — trust labels + coherent coverage exist; correlation/provider disagreement calculus remains open.
54/55. **true causal model / behavioral invariants** — explicit hypotheses and workflow provenance are not full counterfactual program causality or invariant discovery.
59. **HabitatWorkspace orchestration size** — still an architectural debt; alpha.8 does not refactor merely for aesthetics while integrity work is active.

## D. Evidence still missing

46. **same-model Habitat vs normal repository tools** remains the highest-value unproven product claim. Alpha.8 does not infer coding superiority from mechanism tests or source-byte benchmarks.

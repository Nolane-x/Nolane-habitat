# Writing / Implementation Plan — Habitat alpha.5 Deep Evolution

Date: 2026-08-07

This plan follows the user's Nolane AGI Cognitive System methodology: charter before implementation, rival hypotheses, minimal discriminating probes, explicit unknowns, attention budgeting, checkpoint binding and fail-closed admission.

## 1. Charter

### Goal

Reduce the **cognitive navigation tax** paid by an agent inside a project without weakening source authority, mutation safety or evidence quality.

### Protected invariants

1. Canonical source files remain source truth.
2. Derived semantic state is rebuildable and provenance-bound.
3. Exact source is loaded only when decision value justifies it.
4. Precise providers may supersede weaker evidence only inside proven boundaries.
5. Background/watch/telemetry systems never become integrity authorities.
6. Consequential mutation is digest/revision bound and previewable.
7. Missing capability is disclosed rather than relabeled as success.
8. A benchmark harness failure invalidates that evidence run.

### Non-goals

- desktop/OS replacement;
- generic shell as the primary agent interface;
- universal language-server parity;
- claiming token or coding-success improvements without same-model controlled trials;
- hiding source under a proprietary database format.

## 2. Belief ledger

### B1 — Precision overlays improve graph quality

Rival: AST/import heuristics are already adequate and precision providers add cost without decision value.

Probe: duplicate-symbol and alias fixtures; verify resolved target and preserved unresolved call sites.

Kill criterion: provider cannot improve disambiguation or introduces silent fact loss.

Result: retained with a stricter call-site supersession rule.

### B2 — Whole-domain precision caching is too coarse

Rival: provider startup dominates, so partition caching adds complexity without useful reduction.

Probe: warm, one-file body edit, API-surface edit.

Admission target:

- warm: zero source partition recompute;
- body-only: one source partition recompute;
- surface change: conservative broader invalidation.

Result: retained for Python Jedi and TypeScript traversal partitions.

### B3 — Top retrieval score is enough confidence

Rival: concept coverage is unnecessary because ranking already captures relevance.

Discriminating probe: multi-concept no-gold query containing one common corpus word.

Observed failure: one common term could produce high confidence on the AGI corpus.

Result: belief rejected. Alpha.5 confidence includes indexed concept coverage and explicit abstention.

### B4 — Context packets should behave like virtual memory

Rival: bounded materialization is already sufficient.

Probe: large address space with exact byte budget and stale-context mutation.

Result: virtual pages add explicit addressability, page faults and omission reasons without duplicating source.

### B5 — Runtime/test output should remain transient receipts

Rival: storing failures risks stale noise.

Probe: fail test -> orient task -> fix -> pass -> orient again.

Result: active/resolved evidence lifecycle retained; inactive evidence excluded from live lexical retrieval.

### B6 — Semantic rename is safer than text rename

Rival: repository-wide search/replace is simpler and sufficient.

Probe: imported symbol with local alias + duplicate names + external edit after stage.

Result: semantic rename retained for the Python/Jedi boundary; unsupported languages remain explicit gaps.

### B7 — MCP should replace the internal protocol

Rival: one standard protocol simplifies the product.

Result: rejected. MCP is an optional adapter. Internal protocol remains the typed substrate because Habitat requires capabilities not every host exposes identically and because a compact adapter avoids tool-context flooding.

## 3. Implementation milestones

### M1 — Python static semantic overlay

- Jedi provider probe/version identity.
- Static `goto` calls; no project import/execution.
- semantic relations + occurrences.
- exact call-site supersession.
- provider-partition cache.

Verifier: duplicate symbol + alias + side-effect module + mixed resolved/unresolved calls.

### M2 — TypeScript dirty traversal partitions

- whole project Program/TypeChecker for correctness boundary;
- dirty-source traversal set;
- provider partitions keyed by source digest + API/import surface;
- skip Node process on full warm hit.

Verifier: warm/body-only/API-surface fixture.

### M3 — Merkle project state

- content-addressed derived objects;
- snapshots bound to revisions;
- subtree query and hash-pruned diff;
- rename recognition;
- zero additional source-byte reads.

### M4 — Context virtual memory

- virtual page map;
- symbol and diagnostic page classes;
- metadata-only file pages;
- stale/fault semantics;
- exact-byte budget;
- direct backing-byte race validation.

### M5 — Retrieval calibration

- concept coverage;
- confidence grade;
- abstention recommendation;
- source-prefetch suppression in high-level adapter.

Verifier: known-gold, distractor, no-gold, one-common-term no-gold.

### M6 — Evidence lifecycle

- active evidence storage;
- inspection + context lane;
- targeted/full-suite resolution policy;
- inactive lexical suppression.

### M7 — Semantic rename

- Jedi definition/reference proof;
- exact span mutation;
- multi-file digest-bound transaction;
- alias preservation;
- stale transaction rejection.

### M8 — Runtime semantic assertions

- handle/role/name selection;
- count/state/text/value checks;
- structured failures;
- explicit non-pixel oracle.

### M9 — MCP adapter

- optional dependency;
- 12 composed high-level tools;
- status resource;
- SDK contract-double integration;
- no generic shell exposure.

### M10 — Research/evaluation harness

- executable alpha.5 vertical demo;
- user AGI ZIP stress corpus;
- 200-noise-file context precision harness;
- protocol trace exact-source byte measurement;
- explicit no-model claim boundary.

## 4. Unknown-unknown probes

- Resolved evidence leaking through FTS history.
- Precise provider erasing unresolved call evidence at another line.
- API-surface fingerprints accidentally include function bodies.
- Cache identity failing to include provider version/schema.
- Page faults re-running expensive global reconcile per page.
- No-gold query obtaining false confidence through one common term.
- Semantic rename mutating local aliases or stale source.
- MCP adapter appearing operational when SDK is absent.
- Browser assertion silently falling back to pixels.

Each discovered case must either gain a regression test or remain an explicit documented frontier.

## 5. Admission gates

Alpha.5 release admission requires all of the following from a clean extracted artifact:

1. full test suite green;
2. Python compileall green;
3. all JSON schemas/reports parse;
4. README quick-start executable;
5. alpha.5 vertical demo green;
6. AGI ZIP stress harness green;
7. context precision/no-gold harness green;
8. archive integrity green;
9. manifest file-set and SHA-256 verification green;
10. isolated package import reports exactly `0.1.0-alpha.5`;
11. no unexplained generated cache/build files in delivery;
12. self-audit includes failures as well as successes.

## 6. Claim boundary

Even if deterministic fixture source-byte reduction is large, alpha.5 must not convert bytes directly to tokens or infer agent success. A future same-model A/B must control model, scaffold, repository revision, task, tool permissions, token/time budget, evaluator and repeated runs.

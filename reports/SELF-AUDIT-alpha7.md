# Nolane Habitat 0.1.0-alpha.7 — Self-Audit

## Admission stance
Alpha.7 is admitted only for bounded engineering claims about composable project substrate, semantic region exploration, provider lifecycle, context utilization accounting and workflow provenance. It is not admitted as proof of model/token/coding superiority, Cloudflare compatibility, hostile-code isolation or AGI capability.

## Findings kept visible

### F1 — Manifest compatibility regression
**Observation:** first schema-4 implementation reused legacy `source_authority` as a provider object.
**Risk:** alpha.1–alpha.6 schema consumers would break despite no need to reinterpret the old field.
**Correction:** restore legacy string meaning and add `source_authority_provider` plus `execution_provider`.
**Verifier:** alpha.1, alpha.6 and alpha.7 schema-contract tests all pass.

### F2 — Unbounded Jedi Project retention
**Observation:** an initial workspace-lifetime global Jedi cache made long regression runs pathologically slow when historical callers did not close every workspace.
**Rival hypothesis tested:** every semantic provider benefits from persistent project/session state.
**Result:** rejected for unbounded Jedi retention.
**Correction:** retain durable per-source semantic output partitions and use a bounded four-Project LRU that self-prunes deleted roots; close is no longer required for boundedness.
**Verifier:** Python precision tests + full 130-test successful run; provider status exposes cache bound.

### F3 — TypeScript LanguageService stdio lifecycle
**Observation:** persistent TS service initially emitted `ResourceWarning` for open pipes.
**Correction:** close stdin/stdout/stderr deterministically after process termination.
**Verifier:** alpha.7 provider tests under `ResourceWarning` escalation.

### F4 — Green suite did not initially imply clean host shutdown
**Observation:** all tests could print `OK` while process-shared runtime services remained alive beyond the runner.
**Correction:** add idempotent host-level `shutdown_runtime_services()` covering TS sessions, Jedi cache and shared browser engine; register it after runtime modules so it drains first at process exit.
**Verifier:** lifecycle regression + a normal full-discovery run completed 130/130 and returned to the shell.

### F5 — Detached executor source mutation ambiguity
**Observation:** separating execution placement from source authority creates a dangerous implicit-write-back temptation.
**Correction:** if an executor rooted outside canonical authority changes project paths, `CompositeProjectBackend` fails closed until an explicit durable write-back bridge exists.
**Verifier:** dedicated mutation probe preserves authority and compiler mirror unchanged.

### F6 — Explorer must not become another source dump
**Observation:** a file-level localization API would still force the solver to read whole files.
**Correction:** `workspace.explore` emits symbol/diagnostic line regions under a hard line budget and reads zero exact source bytes; exact source remains behind Context VM.
**Verifier:** 202-file distractor benchmark selects 3 lines for auth and billing with zero noise; no-gold abstains.

### F7 — Utilization metrics can overclaim
**Risk:** treating bytes as tokens or unrated pages as useless would create false evidence.
**Correction:** context-efficiency output explicitly labels source bytes, explicit feedback, and unrated uncertainty; no automatic token conversion or waste inference.
**Verifier:** schema + context-efficiency regression.

### F8 — Stress summary consumer used stale report key
**Observation:** AGI stress itself completed, but a summary helper expected old nested key `compile` instead of alpha.7 `compiled_files`.
**Correction:** raw report retained; consumer corrected to current typed report shape.
**Verifier:** current stress report parses and reports 251 files, 0 warm compiles, 251 reuse.

### F9 — Combined admission commands show runner latency variance
**Observation:** some long combined tool invocations exceeded external runner time limits even though isolated gates were fast and a normal full suite completed in ~35 seconds.
**Handling:** do not convert timeout into a core PASS or FAIL. Release admission records a successful full-discovery run and additionally runs clean-extracted test shards/empirical gates independently.
**Remaining risk:** CI/runtime scheduling variance should be measured on future hosts.

## Unknowns deliberately retained
- no real Cloudflare Computer source/execution adapter;
- no production durable write-back bridge from detached remote executors;
- no controlled same-model filesystem-vs-Habitat coding benchmark;
- no proof that line/source-byte reduction becomes token reduction for arbitrary models;
- Java/LSP/SCIP precision remains incomplete;
- workflow causal graph is not full dynamic program causality.

## Source-tree admission
- full discovery: 130 / 130 PASS in a successful normal-exit run;
- compileall: PASS;
- schema/version/CLI quick-start: PASS;
- alpha.7 demo: PASS;
- local/mirror + detached-executor composition: PASS;
- 202-file explorer benchmark: PASS;
- supplied AGI-ZIP stress: PASS.

Final release remains conditional on independently verified packaged-artifact gates.

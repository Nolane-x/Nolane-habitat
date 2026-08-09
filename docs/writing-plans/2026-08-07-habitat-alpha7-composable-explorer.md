# Writing Plan — Habitat alpha.7 Composable Substrate + Semantic Explorer

## Charter
Goal: make Habitat's cognition independent of source/execution placement while reducing the source material an agent must fault during project exploration.

Non-goals: cloud transport, arbitrary remote write-back, universal language precision, model-weight learning, desktop/OS automation, claims of token or coding-success improvement.

Protected invariants:
1. canonical source remains ordinary project bytes;
2. Semantic Twin is rebuildable derived state;
3. old manifest semantics remain readable;
4. low-confidence retrieval may abstain;
5. detached execution cannot silently become source authority;
6. optional instrumentation/service failures cannot change source truth.

## Hypotheses and kill criteria
- H1: SourceAuthority and ExecutionProvider can be composed without changing local/mirror semantic answers. Kill if equivalence fixture diverges.
- H2: persistent TypeScript service reduces repeated provider setup while remaining bounded. Kill if process lifecycle leaks or unchanged refresh starts provider unnecessarily.
- H3: a bounded Jedi cache can preserve reuse without requiring callers to close every workspace. Kill if full suite does not terminate or cache cardinality is unbounded.
- H4: line-budget explorer can retrieve gold semantic regions in distractor fixtures while reading zero source bytes. Kill if noise fills region budget or no-gold chooses least-bad source.
- H5: page-fault/utilization ledger improves observability without converting bytes to tokens or unrated context to waste. Kill if report makes either inference.
- H6: workflow causal graph can connect context→transaction→revision→run/evidence without pretending to be program causality. Kill if provenance edges cannot be reproduced from stored ledger.

## Milestones
M1 composable substrate contracts and compatibility façade.
M2 schema-4 provider identity with legacy-field preservation.
M3 detached-executor mutation fail-closed probe.
M4 bounded persistent semantic services.
M5 line-budget explorer + protocol surface.
M6 context fault/utilization ledger.
M7 cross-revision causal graph.
M8 deterministic runtime-service shutdown.
M9 schema contracts and backward regression suite.
M10 200-distractor explorer benchmark.
M11 supplied AGI-ZIP stress.
M12 independent packaged-artifact admission.

## Admission
Release only when:
- full suite passes and process terminates normally;
- archive/schema/manifest contracts pass;
- local vs mirror semantic equivalence passes;
- detached executor mutation is rejected;
- credential/billing distractor targets are selected with zero noise regions;
- no-gold abstains with zero source bytes;
- AGI corpus warm refresh reuses all unchanged files/provider partitions;
- final ZIP is independently rehashed and tested after clean extraction.

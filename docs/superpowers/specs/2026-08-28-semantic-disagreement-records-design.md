# Semantic Disagreement Records Design

## Status

Approved continuation of Foundation Convergence Wave 1 after merged SCIP runtime PR #7.

## Goal

Make disagreements between admitted semantic providers explicit, revision-bound evidence instead of silently hiding them behind provider precedence, while preserving source authority, existing compiler output, and mutation boundaries.

## Scope

This wave adds a provider-neutral claim/disagreement model plus an automatic comparison producer for the existing common `parse` capability. It does not persist disagreement records to SQLite, adjudicate a winner, change compiler provider precedence, change MCP/agent protocol, or grant any semantic provider source/mutation authority.

LSP and SCIP remain read-only query providers. Their query envelopes can be normalized into the same claim model later during Truth/Evidence Convergence; this wave does not invent a false common query interface.

## Invariants

1. Source bytes remain executable truth.
2. Provider admission remains the only semantic selection gate.
3. Authority is never inferred from confidence, trust grade, provider count, or majority vote.
4. Primary `compile_file()` behavior and provider precedence are unchanged.
5. A provider failure/unavailable/incomplete result is not negative evidence.
6. Absence conflicts are emitted only when every compared provider completed the relevant comparison.
7. Every claim is bound to workspace revision, source path, source digest, provider identity/fingerprint, trust, capability, and canonical value.
8. Every disagreement has a deterministic ID and `resolution="unresolved"` in this wave.
9. No disagreement path exposes mutation operations or changes `source_authority=False` / `mutation_authority=False` contracts.
10. Comparison is bounded by provider, claim, and disagreement limits.

## Architecture

### `habitat/semantic/disagreement.py`

Pure data/normalization/comparison layer.

`SemanticClaim` contains:
- deterministic `id`;
- `subject_key`;
- `capability`;
- `provider_id` and optional `provider_fingerprint`;
- `revision`;
- `path` and `source_digest`;
- `trust`;
- canonical JSON-compatible `value`;
- provenance/evidence tuple.

`SemanticDisagreementRecord` contains:
- deterministic `id`;
- subject/capability/revision/source digest;
- kind: `presence-conflict`, `attribute-conflict`, `location-conflict`, or `relation-conflict`;
- participating claims;
- `comparison_complete`;
- `resolution="unresolved"`.

Canonical hashes use sorted compact JSON and SHA-256. Records are deterministic for the same provider evidence and revision.

### `habitat/semantic/comparison.py`

Workspace-facing bounded producer for the existing common `parse` lane.

For one source file it:
1. resolves language and source digest;
2. gets all admitted `parse` providers for that language from `SemanticAdmissionRegistry`;
3. executes at most four providers independently;
4. converts complete `SemanticParseResult` outputs into symbol/relation/diagnostic claims;
5. records provider failures/unavailable outputs as incomplete comparison state, not negative claims;
6. compares normalized claims and returns a bounded read-only report.

Default limits:
- providers: 4;
- claims: 5,000 total;
- disagreements: 2,000;
- source input: existing compiler parse-size bound (5 MiB).

### `HabitatWorkspace.semantic_disagreements(path)`

A read-only facade in `habitat/workspace.py`. It reconciles source state first, then runs bounded semantic comparison on current source bytes and current revision. No index is auto-activated and no new process is started except behavior already inherent in an explicitly admitted provider.

`semantic_fabric()` gains only diagnostic counts/claim-boundary text if a comparison has been explicitly requested during the workspace lifetime; it does not auto-run comparisons while reporting Fabric state.

## Claim normalization

### Symbols

Subject key: `symbol:<path>:<qualified_name>:<kind>`.

Canonical value includes name, qualified name, kind, language, start/end lines, and signature. Range-only changes are classified as `location-conflict`; other unequal fields are `attribute-conflict`.

### Relations

Subject key is derived from source identity, relation kind, and normalized target identity. Unequal targets/kinds for otherwise matching relation slots become `relation-conflict`.

### Diagnostics

Diagnostics are retained as claims/provenance but do not create absence conflicts unless every provider completed. This prevents a crashed parser from being treated as evidence that a diagnostic does not exist.

## Completeness and negative space

A comparison is complete only if at least two providers were selected and every selected provider returned `available=True` without exception and without an explicitly incomplete parse marker.

When comparison is incomplete:
- positive conflicts between claims that both exist may still be reported;
- missing-claim/presence conflicts are suppressed;
- report contains provider-level failure reasons.

## Ordering and determinism

Provider execution follows registry precedence but output claims/disagreements are sorted by deterministic IDs. No result depends on dictionary insertion order, wall clock, or provider response order.

## Failure handling

- invalid path or path escape: fail closed before provider execution;
- binary/oversized source: return bounded incomplete report, never parse unbounded bytes;
- provider exception: capture exception class and bounded message; continue other providers;
- claim/disagreement limit exceeded: stop producing additional objects, set `truncated=True`;
- source digest/revision are captured once before provider execution and verified again after collection; drift invalidates the report with a stale error rather than emitting mixed-revision evidence.

## Testing

TDD must cover:
- identical providers -> zero disagreements;
- signature/kind conflict -> deterministic attribute conflict;
- range-only difference -> location conflict;
- one provider missing a symbol with all providers complete -> presence conflict;
- provider failure/unavailable -> no false presence conflict and comparison incomplete;
- deterministic IDs independent of provider order;
- bounds/truncation;
- source digest/revision drift rejection;
- workspace facade path containment and no automatic comparison from `semantic_fabric()`;
- semantic trust/disagreement never authorizes mutation;
- complete Ubuntu/Windows × Python 3.10/3.14 CI plus CodeQL on exact PR head.

## Exit criteria

1. Provider-neutral claim/disagreement engine exists and is deterministic.
2. Automatic parse-lane comparison works only over admitted providers.
3. Incomplete providers cannot manufacture negative-space conflicts.
4. Current revision/digest are present on every emitted claim/record.
5. Primary compiler behavior is unchanged.
6. No `_workspace_core.py`, MCP, agent protocol, workflow, or storage schema change.
7. Full matrix and CodeQL are green on exact head before merge.

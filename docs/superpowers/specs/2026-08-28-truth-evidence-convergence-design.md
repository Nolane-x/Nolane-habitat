# Truth / Evidence Convergence — Foundation Convergence Wave 2

**Status:** approved roadmap implementation design

## Context

Foundation Convergence Wave 1 established provider-neutral semantic evidence across compiler, Tree-sitter, LSP, SCIP, and explicit semantic disagreement records. The repository already stores source records, symbols, relations, diagnostics, occurrences, generic evidence, runtime facts, effect/dataflow facts, epistemic items, and memories. Those records currently use several overlapping notions of `trust`, provenance, confidence, freshness, and action safety.

Wave 2 does **not** replace those stores. It introduces a small constitutional layer that can answer four questions consistently:

1. What kind of authority does this claim actually have?
2. What source/revision/provenance is the claim bound to?
3. Is the claim stale or contradicted by another claim?
4. May this kind of claim authorize a specific action?

The design is adapter-first so existing tables, compiler behavior, semantic admission, MCP/protocol surfaces, and mutation recovery remain intact.

## Non-negotiable invariants

1. **Authority is not confidence.** Confidence may inform reasoning; it never raises action authority.
2. **No implicit authority escalation.** Reformatting, remembering, summarizing, voting, majority agreement, or repeated observation cannot promote a claim to a stronger authority class.
3. **Canonical source remains authoritative.** Exact source bytes or immutable source snapshots are the only `SOURCE_EXACT` basis.
4. **Semantic evidence remains read-only unless an operation explicitly allows it.** LSP/SCIP/compiler semantic claims do not authorize source replacement merely because they are precise.
5. **Memory never becomes authority through recall.** A recalled item records its original authority when known, but the recalled wrapper itself is `MEMORY_RECALLED`; actions requiring direct evidence must revalidate against a current authoritative source.
6. **Freshness is explicit.** Revision/source digest/provider/runtime bindings are checked rather than inferred from age or confidence.
7. **Contradictions are retained.** The kernel projects competing claims; it does not silently pick a winner.
8. **No storage rewrite.** Existing evidence tables and record schemas remain valid in this wave.
9. **No semantic auto-execution.** Truth projection must not start LSP, load SCIP, or run provider comparison implicitly.
10. **No protocol drift.** MCP and public wire contracts are unchanged in this wave.
11. **Mutation compatibility is preserved.** Direct source mutations keep their current digest/policy checks. Wave 2 replaces only ad-hoc authority checks with explicit declarations where behavior can remain identical.
12. **Python 3.10 compatibility.** Do not rely on `enum.StrEnum` or newer-only language features.

## Authority classes

Implement the architecture taxonomy as string-valued enum members:

- `SOURCE_EXACT`: exact canonical source bytes or an exact immutable source snapshot.
- `OBSERVED_EXACT`: direct external/runtime observation bound to the identity that produced it.
- `COMPILER_PRECISE`: compiler/LSP/SCIP-derived semantic evidence with provider provenance.
- `PARSER_DERIVED`: deterministic syntax/parser-derived evidence.
- `HEURISTIC_DERIVED`: deterministic heuristic interpretation or conservative legacy derived evidence.
- `MODEL_INFERRED`: model-generated interpretation or hypothesis.
- `MEMORY_RECALLED`: recalled knowledge. Original authority may be retained as provenance, but recall itself grants no stronger action authority.

There is deliberately **no numeric ordering API**. Authorization is expressed as an explicit set of accepted authority classes. This prevents accidental rules such as “confidence 0.99 model inference is stronger than parser evidence” or “semantic is close enough to exact”.

### Legacy trust adapter

Existing `TrustGrade` values remain supported and are mapped conservatively:

- `exact` -> `SOURCE_EXACT`
- `semantic` -> `COMPILER_PRECISE`
- `parser` -> `PARSER_DERIVED`
- `heuristic` -> `HEURISTIC_DERIVED`
- `derived` -> `HEURISTIC_DERIVED`

Specific adapters may provide stronger, more precise classification only when the source contract proves it. For example a verified process exit receipt can be `OBSERVED_EXACT`; a generic row with `trust='derived'` cannot.

## Normalized claim model

Add a pure immutable `TruthClaim` representation. It is an adapter/projection object, not a replacement database row.

Required fields:

- stable claim `id`
- `subject` — canonical identity of the thing the claim is about
- `predicate` — canonical property/relation name
- canonical `value` plus `value_digest`
- `authority_class`
- optional legacy `trust`
- optional `confidence`, stored independently from authority
- `revision`
- optional `path`
- optional `source_digest`
- `producer` / `source`
- optional `provider_fingerprint`
- optional `observed_at`
- optional `origin_claim_id`
- optional `origin_authority_class` for memory/recalled wrappers
- immutable provenance mapping

Claim IDs and value digests use deterministic canonical JSON + SHA-256. Mapping key order must not affect identity. Claim identity must include the authority/provenance binding needed to distinguish independent observations while still allowing contradiction projection to group claims by `(subject, predicate, revision)`.

### Claim construction rules

- Source-file digest claims are `SOURCE_EXACT` only when read from the workspace indexed source snapshot and bound to its revision/digest.
- Existing symbols/relations/diagnostics/occurrences use the conservative legacy trust adapter.
- Generic evidence rows use their existing trust mapping unless a dedicated adapter recognizes a stronger observation contract.
- Semantic disagreement `SemanticClaim` values adapt to `COMPILER_PRECISE` for `semantic`, `PARSER_DERIVED` for `parser`, etc., while preserving provider fingerprint/provenance.
- Epistemic/model hypotheses are `MODEL_INFERRED` unless their payload explicitly references source evidence; references do not promote the hypothesis itself.
- Memory rows are `MEMORY_RECALLED`. If their provenance carries a valid original authority class, retain it in `origin_authority_class`; never use that field as direct mutation authorization without revalidation.

## Claim adapters

Create small adapters rather than a monolithic migration:

1. `claim_from_file_record(...)`
2. `claim_from_symbol_record(...)`
3. `claim_from_relation_record(...)`
4. `claim_from_diagnostic_record(...)`
5. `claim_from_occurrence_record(...)`
6. `claim_from_evidence_row(...)`
7. `claim_from_semantic_claim(...)`
8. `claim_from_epistemic_item(...)`
9. `claim_from_memory(...)`

Each adapter is deterministic and side-effect free. It accepts an explicit revision/provenance context rather than opening the database or executing providers itself.

Not every adapter must expose every source-specific field. Missing provenance is represented as missing/unknown; it is never invented.

## Action authority declarations

Introduce explicit, inspectable declarations for source mutation operations. This wave does not redesign the mutation engine.

A declaration records:

- operation name
- authority mode (`direct-source` or `evidence-anchor`)
- accepted evidence authority classes, if applicable
- whether canonical source authority is required
- whether source digest binding is required
- rationale

Initial declarations preserve current behavior:

- `replace_text`: direct canonical source + digest binding; no derived evidence anchor.
- `replace_span`: direct canonical source + digest binding; no derived evidence anchor.
- `replace_symbol_source`: evidence anchor must be exactly `SOURCE_EXACT`, plus canonical source/digest validation.
- `create_file`: canonical source-authority capability/policy; no pre-existing evidence anchor.
- `delete_file`: direct canonical source + digest binding.
- `move_file`: direct canonical source + digest binding.

`replace_symbol_source` is the first enforcement integration: replace the façade's ad-hoc `symbol['trust'] == 'exact'` check with the declaration/kernel helper while preserving the same external pass/fail behavior and error boundary.

No declaration may authorize an operation solely from confidence.

## Contradiction and staleness projection

Introduce pure projection types/functions over normalized claims.

### Contradiction

Two current claims contradict when:

- subject, predicate, and comparison scope match,
- they are both eligible for comparison,
- their canonical values differ,
- neither is merely a stale historical version of the other.

A contradiction record contains deterministic ID, grouped claim IDs, subject/predicate, revision/scope, authority classes present, status `unresolved`, and reason. It does not rank or adjudicate winners.

Semantic disagreement records adapt naturally into this projection rather than being discarded or silently resolved.

### Staleness

A claim is stale when any binding it explicitly carries is no longer true, including:

- claim revision differs from the current workspace revision where revision freshness is required,
- a path-bound source digest differs from current canonical/indexed digest,
- provider/runtime fingerprint has been revoked or replaced when the adapter supplies that lifecycle evidence.

The generic pure projection handles revision and digest evidence supplied to it. Runtime-provider lifecycle checks stay in the existing LSP/SCIP managers; their output can be adapted later without duplicating lifecycle ownership.

Stale claims are retained and marked; they do not become negative evidence and do not authorize actions.

## Workspace projection surface

Expose a bounded, explicit read-only workspace projection, tentatively `truth_projection(...)`, that adapts already-materialized/store-resident evidence. It must:

- never run semantic providers,
- never start LSP/SCIP,
- never refresh source implicitly,
- fail closed or mark claims stale when current bindings do not match,
- bound output count,
- return normalized claims plus contradiction/staleness summaries,
- leave existing `semantic_disagreements()` explicit and separate.

The first workspace projection should support source-file/symbol/diagnostic/relation/occurrence/evidence rows already in Store. Semantic disagreement claims may be supplied explicitly from an existing comparison result; the projection must not trigger comparison itself.

No MCP operation is added in this wave.

## Compatibility strategy

- Keep `TrustGrade` and existing record fields unchanged.
- Do not migrate the `evidence` table.
- Do not modify compiler provider selection.
- Do not modify semantic admission.
- Do not modify transaction journal/recovery semantics.
- Keep existing public workspace methods and wire names.
- Add new truth modules and a narrow workspace façade only.
- Replace the one ad-hoc symbol mutation authority check through the new declaration helper only after characterization tests prove behavior equivalence.

## Security / correctness boundaries

- Unknown trust values map to no authority and fail closed for action authorization.
- Unknown authority enum strings are rejected rather than coerced.
- Canonical JSON serialization rejects non-serializable claim values rather than falling back to `repr`.
- Path/digest provenance is data, not proof by itself; `SOURCE_EXACT` construction is limited to adapters that possess an exact source contract.
- A collection of weaker claims never automatically aggregates into a stronger authority class.
- Contradiction resolution is intentionally deferred; Wave 2 exposes conflict rather than inventing adjudication.

## Deferred

- Evidence-table deletion/migration.
- Full TruthService/Core service decomposition (Wave 3).
- learned authority policy.
- probabilistic calibration.
- automatic contradiction adjudication.
- distributed/federated trust.
- new MCP/protocol operations.
- persistent normalized claim store unless later evidence shows the adapter projection is insufficient.
- Learning Plane policy promotion.

## Exit criteria

Wave 2 is complete when:

1. authority taxonomy exists with no numeric ranking API;
2. legacy trust mapping is conservative and covered by tests;
3. normalized claims are deterministic and confidence-independent from authority;
4. adapters cover current core source/semantic/evidence structures without schema migration;
5. contradiction and stale projection is deterministic and fail-closed;
6. mutation operation declarations are inspectable;
7. `replace_symbol_source` uses the authority kernel and preserves exact-anchor behavior;
8. semantic/model/memory claims cannot authorize exact-source replacement;
9. workspace truth projection is explicit, bounded, and causes no semantic-provider execution;
10. `_workspace_core.py`, storage schema, MCP/protocol, and compiler selection remain unchanged unless a separately proven defect requires change;
11. full Ubuntu/Windows Python 3.10/3.14 CI, compatibility/recovery/reproducibility/Semgrep and CodeQL are green on the exact PR head;
12. review threads are resolved and the exact verified head is merged with head-SHA protection.

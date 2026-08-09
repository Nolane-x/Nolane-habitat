# Alpha.6 Research Notes — Backend Substrate + Cognitive Continuity

Date: 2026-08-07

## Research question

Habitat must remain an **agent cognition layer over a project**, not become another virtual computer. The alpha.6 question is therefore:

> Can source authority and execution placement become pluggable without weakening Habitat's Semantic Twin, exact-source integrity, context calibration, transactions, evidence or checkpoint semantics?

## External comparison: Cloudflare Computer

Current public Cloudflare Computer material describes a persistent workspace/filesystem backed by Durable Object SQLite plus an execution surface with pluggable runtime backends. Its agent-facing defaults remain fundamentally filesystem/runtime operations such as reading, writing, listing/editing files and executing work.

Habitat adopts the useful boundary — authoritative workspace and replaceable execution placement — but does **not** copy filesystem-first cognition. The differentiated layer remains:

- Semantic Twin;
- symbol/reference/occurrence graph;
- Context Compiler and selective abstention;
- virtual source pages;
- evidence lifecycle;
- transactional semantic edits;
- affected-test reasoning;
- UI semantic state;
- provenance-bound long-horizon state.

Cloudflare Computer is therefore treated as a potential future backend class, not as the product Habitat should become.

Research source: https://github.com/cloudflare/computer and `packages/computer/README.md` (audited 2026-08-07).

## Retrieval research implication

Recent repository-exploration benchmarks reinforce that file-level retrieval alone is insufficient. SWE-Explore emphasizes line-level coverage/ranking/context efficiency, while Agent Retrieval Bench includes natural no-gold cases and demonstrates a selective-retrieval calibration gap.

Habitat alpha.6 therefore invests in:

- exact source page planning rather than broad reads;
- low-confidence abstention;
- context utility as a bounded prior, never authority;
- feedback that cannot invent a candidate;
- no-gold planner suppression;
- causal episode provenance instead of narrative-only memory.

Research sources:

- SWE-Explore: https://arxiv.org/abs/2606.07297
- Agent Retrieval Bench: https://arxiv.org/abs/2607.24882

## Rival architectures considered

### Rival A — filesystem/runtime wrapper

`read/write/exec` becomes the primary interface and Semantic Twin is optional metadata.

Rejected because it reproduces the navigation tax Habitat exists to remove.

### Rival B — semantic database becomes canonical source

Semantic objects become authority and source files are exported views.

Rejected because compiler/runtime truth and ordinary project interoperability would become fragile. Canonical source bytes remain outside the Semantic Twin.

### Rival C — backend abstraction owns both cognition and source semantics

Each backend supplies its own indexing/retrieval model.

Rejected because semantic behavior would drift by backend. Alpha.6 requires local and remote-like contract doubles to yield equivalent semantic answers for the same canonical project.

### Selected architecture

`ProjectBackend` owns source authority/materialization/execution placement. Habitat owns compilation, graph, context, evidence, mutation policy and cognition state.

The first non-local implementation is deliberately named `DirectoryMirrorBackend`: it is a contract double proving authority != compiler mirror. It is **not** presented as a Cloudflare integration.

## Unknowns retained

- A production remote backend needs a real change-feed/listing/digest contract; DirectoryMirror is only a local proof.
- Cloudflare Computer APIs are TypeScript/Workers-native; a production adapter needs a transport/deployment design rather than speculative Python calls.
- Multiple runtime backends may require an execution policy above capability discovery. Alpha.6 records execution provenance but does not expose arbitrary runtime selection to the model.
- Utility feedback can become stale or biased over long horizons; alpha.6 bounds its score effect but does not claim learned optimal retrieval.
- Work-episode links are causal workflow provenance, not proof of semantic/program causality.

## Alpha.6 admission thesis

Admit alpha.6 only if:

1. local alpha.5 behavior remains regression-clean;
2. remote-like authority can be separated from semantic materialization;
3. exact source reads/writes go through authority, not mirror shortcuts;
4. local vs mirror fixture produces equivalent semantic answers and canonical edits;
5. execution receipts bind backend provenance;
6. targeted backend hydration can operate without whole-project enumeration when exact candidate paths are known;
7. context feedback remains bounded/non-authoritative;
8. no-gold page planning reads zero source bytes;
9. work episodes bind context → transaction → revision → verification;
10. checkpoint/resume binds backend identity and may bind the active work episode;
11. supplied AGI corpus warm reuse remains intact;
12. every failure found during implementation is retained in self-audit.

# Alpha.8 Architecture — Integrity Before Intelligence

## Charter
Alpha.8 converts the external alpha.6 failure report into executable invariants. The release is admitted only when Habitat cannot silently reason from known-stale state, cannot report an ambiguous post-side-effect error for high-level mutation, and can distinguish model-visible source from authority/compiler/index I/O.

## Core architecture changes

### 1. Perception integrity
`reconcile()` is no longer size+mtime only. POSIX local authorities bind size, mtime, ctime and inode, hash only changed candidates, then incrementally admit them. Windows cannot treat `st_ctime` as a POSIX change-time oracle, so alpha.8 deliberately falls back to deep content verification until a native change-journal authority exists. `refresh()` remains the explicit whole-project content-hash scrub.

### 2. Sparse authoritative source I/O
Compiler artifacts store line checkpoints. Context VM and exact symbol inspection request line ranges from `SourceAuthority` rather than reading the complete file. Every result separates:
- `agent_visible_source_bytes`;
- `backend_authority_bytes_read`;
- compiler/index accounting where available.

### 3. Source admission policy
The source enumerator respects `.gitignore` and `.habitatignore`. Hard ignores are restricted to VCS/cache/control directories rather than generic names such as `build/` or `dist/`. Persistent Habitat state is rejected when placed inside the source root.

### 4. State-machine enforced work episodes
Episode identity/status is validated before staging or verification side effects. Stale contexts cannot open a new episode. Completed episodes cannot retain or later commit staged world mutations.

### 5. Crash-recoverable local mutation
Local mutation uses a write-ahead journal with prepared/applying/committed/rolled-back markers and startup recovery. Text mutation preserves dominant newline style and ordinary file mode/metadata. Structural `create_file`, `delete_file`, and `move_file` operations are first-class transaction operations. This is local crash recovery, not distributed 2PC.

### 6. Retrieval and confidence hardening
Task tokenization is Unicode-aware. Symbol terms are persisted in an inverted index rather than requiring full symbol scans for normal term lookup. Long tasks use an evaluated-term denominator. Multi-concept high confidence requires coherent support rather than unrelated concept existence across arbitrary files. Low-confidence no-gold tasks can abstain.

### 7. Evidence and execution accounting
Execution output is streamed to bounded temporary storage before a capped prefix is admitted to the receipt. Total stdout/stderr bytes remain visible. Common secret patterns are redacted. Receipts include an environment fingerprint and explicit unsandboxed posture. Test-failure evidence is resolved only within the executed capability/scope.

### 8. Hypothesis / experiment cognition
Habitat can persist revision-bound hypotheses, evidence-for/evidence-against links, discriminating experiments and belief updates. Confidence is explicitly an agent belief annotation, not a calibrated probability. The layer supports scientific workflow; it does not claim autonomous causal inference.

## Assurance tiers

### Admitted in alpha.8
- stronger ordinary perception integrity;
- explicit deep integrity scrub;
- sparse exact-source authority reads;
- stale feedback rejection;
- episode side-effect ordering;
- WAL startup recovery for local mutations;
- CRLF/mode preservation;
- source ignore/self-index protection;
- strict protocol type validation;
- bounded execution capture and provenance;
- browser external-network deny-by-default;
- explicit hypothesis/experiment state.

### Still open / production blockers
- OS-enforced sandbox for hostile repository execution;
- network/filesystem/process/memory confinement for local execution;
- encrypted/retention-governed persistent cognitive state;
- distributed/multi-agent transaction ordering and leases;
- production remote change feed / ETag / server-side Merkle;
- precision semantics across Java, Go, Rust, C/C++, C#, Kotlin, Swift;
- framework-complete UI program cognition;
- calibrated uncertainty calculus and full causal/program invariant model;
- same-model Habitat-vs-filesystem coding-success benchmark;
- complete service decomposition of the `HabitatWorkspace` orchestration façade.

## Claim boundary
Alpha.8 demonstrates stronger mechanisms and adversarial regression coverage. It does not establish AGI, universal token savings, production hostile-code safety, complete causal understanding, or coding-agent superiority.

# Release Verification — Nolane Habitat 0.1.0-alpha.8

## Source-tree admission
- historical + alpha.8 test coverage: **152/152 PASS via exhaustive shards**;
- compileall: PASS;
- all JSON schemas and alpha.8 JSON reports parse: PASS;
- CLI/package/version identity: `0.1.0-alpha.8` / `0.1.0a8`;
- one monolithic discovery attempt exceeded the external runner wall-clock and is explicitly **not** counted as a pass.

## RC artifact gate
Artifact: `Nolane-Habitat-0.1.0-alpha.8-RC.zip`

Independent clean-extraction manifest verifier:
- entries: 235;
- missing: 0;
- extra: 0;
- hash mismatches: 0;
- root hash: PASS;
- manifest version: 0.1.0-alpha.8.

Clean RC exhaustive test shards:
- alpha.0–alpha.3: 49 PASS;
- alpha.4: 17 PASS;
- alpha.5: 17 PASS;
- alpha.6: 11 PASS;
- alpha.7 + alpha.8 + compiler/capability/large-file: 36 PASS;
- execution/protocol/Jedi/schema/source/storage/workspace: 22 PASS;
- **total: 152/152 PASS**;
- compileall: PASS.

## Empirical RC gates
### >1 MB sparse authority I/O demo
- source file: 1,056,985 B;
- agent-visible exact source: 94 B;
- authority bytes read for the page: 8,639 B;
- same-size/restored-mtime change detected: PASS;
- CRLF preserved: PASS;
- executable mode 0755 preserved: PASS;
- `.gitignore` secret excluded: PASS;
- targeted verification: PASS;
- no-gold: LOW / ABSTAIN / 0 source B.

### 202-file explorer
- 200 distractor files;
- credential gold region: PASS, 0 noise, 128 B solver source;
- billing gold region: PASS, 0 noise, 93 B solver source;
- no-gold: LOW / ABSTAIN / 0 B.

### Backend composition
- local/mirror semantic equivalence: PASS;
- local/mirror exploration equivalence: PASS;
- detached executor mutation fail-closed: PASS;
- canonical authority unchanged after rejected detached mutation: PASS.

### Supplied Nolane AGI ZIP stress
- files: 251;
- symbols: 865;
- occurrences: 4,351;
- ordinary warm reconcile: 0 hashed files, integrity-assisted metadata path;
- explicit deep scrub: 0 compiled / 251 reused / 88,271,461 hash bytes;
- no-gold: LOW / ABSTAIN / 0 source B.

## Package gate
- isolated `pip --target` install with no source-checkout import: PASS;
- imported module path rooted under `/tmp/a8-pkg-target`;
- imported version: `0.1.0-alpha.8`;
- quick-start create/orient: PASS / HIGH confidence;
- compact MCP catalog: 12 tools;
- MCP SDK absent on this host; optional-runtime admission is therefore limited to contract/negative-path behavior.

## Release blockers deliberately not claimed as solved
- hostile repository execution remains unsandboxed on the local provider;
- Windows uses deep perception fallback rather than an efficient native change journal;
- local WAL is not remote/distributed 2PC;
- enterprise retention/encryption/secret governance is incomplete;
- multi-agent distributed concurrency is incomplete;
- broad language semantic parity and same-model coding-superiority evidence remain open.

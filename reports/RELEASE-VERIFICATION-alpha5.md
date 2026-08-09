# Nolane Habitat 0.1.0-alpha.5 — Release Verification

Date: 2026-08-07

## Admission chain

### Source tree
- full test suite: **111/111 PASS**;
- compileall (`habitat`, `tests`, `benchmarks`): PASS;
- all JSON schemas/current JSON reports parse: PASS;
- README quick-start (`create → enter → orient`): PASS, one object, high confidence;
- fresh end-to-end alpha.5 demo: PASS;
- fresh supplied-AGI-ZIP stress: PASS;
- fresh 200-distractor/no-gold context-precision harness: PASS.

### RC archive
Independent verifier over a clean extraction of `Nolane-Habitat-0.1.0-alpha.5-RC.zip`:
- archive integrity: PASS;
- manifest version: `0.1.0-alpha.5`;
- manifest entries: 162;
- missing: 0;
- extra: 0;
- size/hash mismatches: 0;
- independently recomputed manifest root hash: PASS;
- clean-extracted tests: **111/111 PASS**;
- clean-extracted compileall: PASS;
- clean-extracted demo: high confidence, 187 exact-source bytes, semantic rename verification PASS, evidence `1 → 0`, Merkle extra source reads 0, semantic UI assertion PASS, final warm compile 0;
- clean-extracted supplied AGI stress: 251 files / 865 symbols / 4,372 occurrences; warm 0 compiled / 251 reused; Jedi 78 reused / 0 recomputed; no-gold low + abstain;
- clean-extracted 202-file context precision: credential 127 B / billing 92 B / no-gold 0 B, zero noise paths;
- README quick-start: PASS, high confidence;
- isolated package target install/import: PASS, `habitat.__version__ == 0.1.0-alpha.5` and module loaded from isolated target;
- real MCP SDK: absent on this host; correct `build_server()` missing-SDK path fails clearly; contract-double MCP tests: 4/4 PASS.

## Claim boundary

These gates admit the packaged alpha.5 mechanisms on the tested environment/fixtures. They do **not** establish universal LLM token reduction, universal coding-success improvement, persistent TypeScript language-service incrementality, complete Java/LSP/SCIP precision, hostile-code isolation, framework-complete UI provenance, real MCP runtime on this SDK-missing host, or AGI capability.

## Final packaging rule

The final delivery is built only after this report/self-audit are added. The final ZIP is then independently re-extracted and re-verified for manifest/root hash, full tests, demo/stress/precision, quick-start, package import/version and MCP missing-SDK behavior. The final ZIP SHA-256 is intentionally reported outside the archive to avoid self-referential artifact hashing.

# Release Verification — Nolane Habitat 0.1.0-alpha.13

## Source-tree admission
- Historical + alpha.13 regression: **240 / 240 PASS** across completed process shards.
- `compileall`: PASS.
- Observatory JS syntax: PASS.
- 53 machine-readable schema JSON files parse.
- MCP high-level catalog remains 12 tools.
- Cinematic resilience demo: good counterfactual verification PASS; failed world promotion blocked; memory echo suppressed; telemetry secrets absent; loop risk and context thrash visible; observer POST rejected.
- Supplied Nolane AGI corpus: 251 files, 865 symbols, 4,351 occurrences, 29,012 Effect facts, 35,809 Dataflow facts; ordinary warm reconcile hashes 0 files; explicit deep scrub compiles 0 / reuses 251; no-gold abstains with 0 source bytes.

## RC independent artifact gate
- Delivery manifest: **387 listed / 387 actual**, 0 missing, 0 extra, 0 hash mismatch, root hash PASS.
- ZIP integrity: PASS.
- `compileall`: PASS.
- RC regression: **240 / 240 PASS** (66 + 38 + 56 + 54 + 26).
- RC cinematic core scenario (screenshot capture deliberately skipped in this gate): canonical verification PASS, bad-world promotion blocked, redaction/loop/thrash/LOD behavior reproduced.
- RC supplied-AGI stress: 251 files / 865 symbols / 4,351 occurrences; warm hash 0; deep compile 0 / reuse 251; no-gold LOW+ABSTAIN+0B.
- Isolated pip target: wheel `nolane_habitat-0.1.0a13` built and installed; import from `/tmp/a13-pkg-target`, runtime version `0.1.0-alpha.13`; Observatory `index.html/style.css/app.js` packaged.

## Release-tooling findings preserved
- A long combined unittest/matrix invocation is host-sensitive; only completed shard processes are counted.
- Chromium screenshot acquisition can dominate demo wall time on this host. Source-tree screenshot evidence uses the exact live snapshot and production assets when live-loopback Chromium does not complete in time.
- An initial isolated-import smoke omitted `PYTHONPATH=/tmp/a13-pkg-target`; pip itself had succeeded. The verifier was corrected rather than changing package semantics.

## Claim boundary
This verification establishes artifact integrity and mechanism/regression behavior. It does not establish AGI capability, causal completeness, malicious-code sandbox safety, or same-model coding superiority.

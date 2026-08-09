# Release Verification — Nolane Habitat 0.1.0-alpha.11

## Release candidate

- RC file: `Nolane-Habitat-0.1.0-alpha.11-RC.zip`
- RC SHA-256: `b8a10c389c81655013c14bc0231bdcbc7d0662b7ea64eda3c165838d8e65c62e`
- ZIP integrity: PASS

## Independent RC manifest verification

The RC was extracted into a clean directory. A verifier independent from `tools/package.py` recalculated every listed file size/SHA and the manifest root hash.

- listed files excluding manifest: **325**
- actual files excluding manifest: **325**
- missing: **0**
- extra: **0**
- hash/size mismatches: **0**
- root SHA-256 match: **PASS**

## Clean-extracted regression

All selected historical/core test modules were rerun from the extracted RC in four completed process shards:

- alpha0–4: **66/66 PASS**
- alpha5–7: **38/38 PASS**
- alpha8–11: **68/68 PASS**
- core: **26/26 PASS**
- total: **198/198 PASS**

`compileall`: PASS.

A command that attempted to run two RC shards sequentially in one tool invocation was externally cut after the first shard had passed. The unfinished second shard was not counted; it was rerun independently and passed. This is recorded as release-tooling variance, not test failure or PASS.

## Clean RC Observatory vertical demo

- observer HTTP POST mutation attempt: **405 observer-read-only**
- live agents: **2** (Codex, Claude Code)
- graph: **25 nodes / 22 edges**
- activity sequence: **34**
- project memories: **3**
- runtime observations: **4**
- targeted verification: **PASS**
- screenshot captured from real live state: **PASS**
- direct loopback Chromium navigation may be administratively blocked; fallback renders the exact fetched live snapshot with the same packaged UI assets and never substitutes mock state.

## Supplied AGI ZIP stress from RC

Using `Nolane-AGI-Cognitive-System-4.0.0(1).zip`:

- files: **251**
- symbols: **865**
- occurrences: **4,343**
- ordinary warm reconcile hashed files: **0**
- explicit deep scrub compiled/reused: **0 / 251**
- no-gold query: **LOW / ABSTAIN / 0 source bytes**

## Isolated package install

The extracted RC was installed with pip into `/tmp/a11-pkg-target`, then imported from `/tmp` with that target on `PYTHONPATH`.

- runtime version: **0.1.0-alpha.11**
- imported module path: under `/tmp/a11-pkg-target/habitat/`
- packaged Observatory assets: **index.html, style.css, app.js**
- result: **PASS**

## Claim boundary

These gates admit the artifact's implemented mechanisms and release integrity. They do not establish AGI capability, universal semantic-provider coverage, complete runtime causality, hostile-code production safety, or same-model coding-quality superiority.

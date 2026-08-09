# Release Verification — Nolane Habitat 0.1.0-alpha.12

## Release candidate

- RC file: `Nolane-Habitat-0.1.0-alpha.12-RC.zip`
- RC size: **1,911,154 bytes**
- RC SHA-256: `8139b5f6612b24207baa70e612cf9f3e1e06d3945d5c47387deddc91a9c1384e`
- ZIP integrity: **PASS**

## Independent RC manifest verification

The RC was extracted to a clean tree and verified without calling `tools/package.py`.

- listed files excluding manifest: **364**
- actual files excluding manifest: **364**
- missing: **0**
- extra: **0**
- hash/size mismatch: **0**
- manifest root SHA-256: **PASS**
- clean `compileall`: **PASS**

## Clean-extracted RC regression

- alpha0–4: **66/66 PASS**
- alpha5–7: **38/38 PASS**
- alpha8–12: **83/83 PASS**
- core: **26/26 PASS**
- total: **213/213 PASS**

The four completed shard processes are the admission evidence. A combined long-lived orchestrator invocation remains host-sensitive and is not relabelled as PASS.

## Cinematic Observatory vertical demo from RC

- agents: **3** — Codex, Claude Code, Verifier Agent
- graph: **150 nodes / 126 edges**
- Effect facts in focused demo path: **49**
- Dataflow facts in focused demo path: **55**
- Runtime-topology nodes: **16**
- Project-world entities: **18**
- alternative worlds: **2**
- targeted verification: **PASS**
- browser/UI semantic assertion: **PASS**
- observer mutation attempt: **HTTP 405**
- screenshot: **1920×1080**, exact live-snapshot renderer, no mock state

## Supplied Nolane AGI ZIP stress from RC

Using `Nolane-AGI-Cognitive-System-4.0.0(1).zip`:

- files: **251**
- symbols: **865**
- occurrences: **4,351**
- cold static Effect facts: **29,012**
- cold static Dataflow facts: **35,809**
- ordinary warm reconcile hashed files: **0**
- explicit deep scrub: **0 compiled / 251 reused / 251 hashed**
- explorer: **MEDIUM**, 6,608 agent-visible source bytes, 23,119 authority bytes read
- no-gold: **LOW / ABSTAIN / 0 source bytes**

The stress is deterministic mechanism evidence, not an LLM/token/AGI benchmark.

## Isolated package install

A normal isolated build initially failed because this session's package index could not provide the declared build dependency `setuptools>=68`. This occurred before Habitat build code ran. The host already had setuptools 82.0.1.

The RC was then installed with the available backend using:

`pip install --no-build-isolation --no-deps --target /tmp/a12-pkg-target .`

Import was performed from `/tmp`, outside the checkout:

- `habitat.__version__`: **0.1.0-alpha.12**
- module path: under `/tmp/a12-pkg-target/habitat/`
- packaged assets: **app.js, index.html, style.css**
- result: **PASS**

## Claim boundary

These gates establish artifact integrity and the exercised alpha.12 mechanisms. They do not establish whole-program causality/dataflow, universal language/provider parity, production hostile-code safety, unbounded Observatory scale, or coding-model superiority.

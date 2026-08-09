# Release Verification — Nolane Habitat 0.1.0-alpha.14

## Source-tree admission
- Final regression: **257 / 257 PASS** across six completed process shards (66 + 38 + 56 + 69 + 26 + 2); every counted shard exited 0.
- `compileall`: PASS.
- Observatory JS syntax (`node --check`): PASS.
- 56 machine-readable JSON schema files parse.
- MCP high-level catalog remains 12 tools; lower protocol surface is 162 methods including 8 Executive methods.
- Executive-specific regression covers phase skip rejection, hard loop budgets, explicit stop, anti-cosmetic strategy switching, failure memory, verifier semantics, real revision-bound receipts, stale evidence, schema compatibility and >1,000-event tail tamper detection.

## Wheel / isolated artifact gate
- Final runtime package version: `nolane_habitat-0.1.0a14` / `0.1.0-alpha.14`; the wheel is included in the delivery under `artifacts/`.
- Isolated target imports from the installed wheel, not the source checkout.
- New workspace emits manifest schema 10 with `world_model.executive_trajectory=true`.
- Executive Trajectory starts successfully from installed artifact.
- Wheel contains `habitat/executive.py` and Observatory `index.html`, `style.css`, `app.js` assets.
- Workspace close leaves zero TypeScript sessions, Jedi projects, Playwright users and shared browser instances in the smoke process.

## Packaging gate
- Packager excludes `dist`, `build`, `.git`, `.pytest_cache`, `__pycache__`, `*.egg-info`, `.pyc` and `.pyo` transient material.
- Delivery manifest hashes every shipped file except the manifest itself and computes a deterministic root hash.
- ZIP timestamp metadata is aligned to 2026-08-08.
- Final ZIP integrity and manifest reconciliation are performed after the alpha.14 staging directory is frozen.

## Findings preserved
- Long combined provider/browser test invocations can be host wall-clock sensitive. Admission therefore uses only independently completed shard processes; no timeout is renamed PASS.
- An early isolated-wheel smoke used the nonexistent legacy name `Workspace` instead of the shipped `HabitatWorkspace`; the verifier invocation was corrected. The wheel build/install itself was not the cause.

## Claim boundary
This verification establishes artifact integrity and represented runtime/control contracts. It does not establish AGI capability, universal causal completeness, malicious-code microVM safety, or universal program correctness.

# Release Verification — Nolane Habitat 0.1.0-alpha.15

## Source-tree admission
- Test inventory: **260 tests collected**.
- Final unique regression coverage: **260 / 260 PASS** across independently completed module/class process shards: 66 + 38 + 56 + 72 + 26 + 2.
- No timeout or non-exiting combined host is relabeled PASS. The alpha.5 deep suite is counted only from smaller class/resource-boundary shards that each completed successfully.
- `python -m compileall -q habitat`: PASS.
- Observatory JavaScript syntax (`node --check habitat/observatory_assets/app.js`): PASS.
- **56 / 56** machine-readable JSON schemas parse.

## AI Operator admission
- Authoritative observer frame exists even when semantic assertions do not request an assertion screenshot.
- Live frame filenames are Windows-safe despite semantic session IDs containing `:`.
- Pre-action receipts resolve the real semantic target rectangle and normalized pointer coordinates.
- Password-like values are redacted before activity persistence.
- Post-action receipts carry frame sequence, DOM delta, network/console/layout telemetry and current URL.
- Observatory snapshot reconstructs operator state from durable activity receipts and `/api/ui-frame` serves only already-written PNG bytes.
- Historical spectator-only HTML contract remains intact: no `<button>`, `<input>` or `<form>` control elements are introduced by Observatory view switching.

## Truth / security boundary
- The AI cursor is a deterministic visualization of Habitat's semantic browser target, not OS-level cursor capture.
- The browser panel mirrors the Playwright page Habitat actually controls; it is not a second iframe browser state.
- Pixel frames are for human observability only. Semantic/runtime receipts remain the verification oracle.
- The alpha.15 mirror updates at browser observation/action boundaries; it is not claimed to be continuous remote-desktop video streaming.
- Observatory remains loopback/read-only; visualization tabs mutate only local presentation state.

## Wheel / isolated artifact gate
- Wheel built successfully with the installed setuptools toolchain using `--no-build-isolation` because the environment cannot resolve build-isolation dependencies.
- Isolated wheel install imports as **`0.1.0-alpha.15`**.
- Installed wheel contains `observatory_assets/index.html`, `style.css`, `app.js` and `ui/browser_provider.py`; the AI Operator/cursor markup is present.

## Packaging gate
- Delivery packaging excludes transient caches, `dist`, `build`, `.git` and `*.egg-info`.
- `reports/DELIVERY-MANIFEST.json` hashes every shipped file except itself and records a deterministic root hash.
- Final ZIP integrity and manifest reconciliation are performed after the alpha.15 source directory is frozen.

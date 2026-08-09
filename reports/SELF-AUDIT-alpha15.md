# Self Audit — Habitat alpha.15 AI Operator Observatory

## What changed
Alpha.15 deepens the existing cinematic Observatory with an AI Operator surface that displays the authoritative Playwright viewport, semantic target geometry, a synthetic AI cursor, action timeline, click/typing effects, and runtime telemetry. It also adds WORLD / AI OPERATOR / SPLIT observer modes without adding mutation controls.

## Findings fixed during audit
1. A decorative iframe would create a potentially divergent browser state; replaced by a frame mirror from the actual Habitat Playwright runtime.
2. Initial cursor placement could visibly interpolate from the center; first attach now positions immediately and only subsequent actions animate.
3. Semantic session IDs contain `:`; live frame filenames are sanitized for Windows.
4. Visualization `<button>` elements violated the historical spectator-only HTML contract; replaced with non-form `role=tab` surfaces.
5. Sensitive target values could have leaked into visual action receipts; password/credential/payment-like previews are redacted before persistence.
6. Observatory HTTP workers must not touch sync Playwright objects; the browser thread writes stable frames and the read model serves only durable receipts/files.

## Residual limitations
- Frames update at observation/action boundaries, not at video frame rate. A future CDP screencast/WebRTC transport could improve temporal smoothness without changing the receipt contract.
- Cursor position represents the semantic target chosen by Habitat, not raw physical mouse telemetry.
- Some sites may change appearance between action receipts because animations/video continue between captured frames.
- The operator mirror shows what the browser rendered, but correctness still depends on semantic/runtime verification rather than pixels alone.

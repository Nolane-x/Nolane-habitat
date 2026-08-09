# Habitat Observatory alpha.15 — AI Operator Cockpit

Alpha.15 adds a truthful software-action visualization lane to the existing machine-world Observatory. The design goal is cinematic observability without inventing a second browser state.

## Runtime truth path

1. `ui.runtime.open` creates the normal Habitat Playwright page.
2. `BrowserRuntime.observe()` extracts semantic/accessibility/layout state and captures a viewport-only observer frame to `.habitat/artifacts/ui/live/<session>.png`.
3. Before `ui.runtime.act`, `preview_action()` scrolls the semantic target into view, resolves its real bounding box, calculates absolute and normalized pointer coordinates, and privacy-filters any supplied value.
4. `ui.action-started` persists that preview so the Observatory can animate toward the real target.
5. The action executes in Playwright.
6. The post-action observation atomically replaces the stable live frame and increments `observer_frame_seq`.
7. `ui.action-completed` persists the receipt, DOM delta counts, console/network counts, layout issue count, URL and frame sequence.
8. Observatory HTTP threads reconstruct state from SQLite receipts and serve only the already-written frame bytes. They never call Playwright directly.

This separation is deliberate: Playwright synchronous objects are thread-affine, while Observatory HTTP/SSE uses independent worker threads.

## Visual layers

The center stage now has three observer modes:

- **WORLD** — semantic/effect/runtime/cognitive topology.
- **AI OPERATOR** — authoritative browser frame plus simulated AI pointer and action inspector.
- **SPLIT** — world topology and software mirror simultaneously.

AI Operator renders:

- browser-style chrome with runtime URL/session;
- authoritative viewport frame;
- synthetic Nolane AI cursor projected from normalized target coordinates;
- semantic target brackets;
- click pulse and typing trail;
- secret-redaction indication;
- action, pointer, DOM delta, network, console and layout telemetry;
- short visible-intent timeline.

An incoming UI open/action automatically focuses AI Operator unless the observer recently chose a mode manually. Visualization mode tabs change only the local view; they are non-form observer surfaces and do not issue agent/browser commands.

## Security / privacy boundary

- Observatory remains loopback-only and rejects mutation HTTP verbs.
- `/api/ui-frame` only accepts a restricted session-id character set and only reads the `artifacts/ui/live` directory.
- Password/secret/token/card-like value targets are redacted before activity persistence.
- Observer frames are never fed into semantic pass/fail decisions.
- The synthetic cursor is not OS-level cursor recording and does not claim access to private model reasoning.

## Research basis

The interaction model borrows useful observability ideas from Playwright Trace Viewer: action timelines, exact click target visualization, before/after state and separation of screenshots from semantic/log/network evidence. The alpha.15 implementation adapts those ideas to a live agent workspace rather than a post-run test trace.

Reference: https://playwright.dev/docs/trace-viewer

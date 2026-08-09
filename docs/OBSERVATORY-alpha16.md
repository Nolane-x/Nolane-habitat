# Habitat Observatory alpha.16 — Continuous AI Operator

Alpha.16 keeps WORLD / AI OPERATOR / SPLIT as spectator-only views, but the operator viewport can now advance independently of Playwright actions.

## Transport ladder
1. `cdp-websocket-live`: Chromium exposes a temporary DevTools endpoint on `127.0.0.1`; Habitat obtains the current page target ID on the owning Playwright thread, detaches that session, then a dedicated WebSocket worker owns only the raw CDP socket and `Page.startScreencast`/frame acknowledgements. It never calls Playwright.
2. `cdp-screencast-cooperative`: if raw transport is unavailable, a normal Playwright CDP session publishes frames while the sync Playwright loop is pumped.
3. `snapshot-fallback`: explicit viewport capture remains available when screencast transport is unavailable.

The Observatory polls atomic stream metadata and exact versioned PNG frames. Session/stream epoch changes invalidate queued cursor and typing animation so frames from a previous browser session cannot visually bleed into the next one.

## Security and privacy
The raw DevTools endpoint is loopback-only and uses an exact allowed WebSocket origin. Browser routing denies project JavaScript access to that port even when external browser networking is explicitly permitted. Live frame artifacts are ephemeral: a bounded ring is removed on session close and crash-left live artifacts are removed when a new BrowserRuntime starts.

Sensitive DOM values, ARIA text, inline handlers, console assignments and common credential-bearing URL parameters are redacted before public read-model/activity persistence. Sensitive typing does not expose value length.

## Claim boundary
The viewport is a human observability surface. Habitat does not use screencast pixels to declare semantic correctness. CDP video cadence is browser/host dependent and is not an OS-input or remote-desktop recording.

# Alpha.16 forensic findings

The alpha.16 pass applied the Nolane-AGI style of state/evidence/lifecycle checking to the AI Operator path. Fixed findings include:

1. Observatory JavaScript contained literal NUL separators, causing text tooling to classify the source as binary.
2. Session switch used monotonic `Math.max` frame counters across sessions, allowing a high old sequence to suppress a new session's low sequence.
3. Human-observer frame filenames used lossy sanitization, so distinct session IDs could collide on Windows-safe names.
4. Live browser pixels survived normal close/crash paths longer than intended. Alpha.16 uses an ephemeral bounded ring and cleanup.
5. Password values were redacted in DOM observations but could reappear in Playwright ARIA snapshots.
6. Sensitive typing receipts exposed secret length even when content was redacted.
7. JSON-style console assignments and inline handler source could retain credential values after the original fill redaction.
8. Credential-bearing target/page URLs could reach the public read-model/activity layer unsanitized.
9. Stream metadata could be published from fields observed at different moments, producing a torn `seq/file/source` tuple under concurrency.
10. Action-boundary CDP callbacks did not advance while the owning sync Playwright thread was idle; alpha.16 adds an independent raw CDP WebSocket transport.
11. The new DevTools loopback port created a local attack surface because the prior project policy allowed arbitrary localhost traffic. Project-page access to that privileged port is now denied in all network modes.
12. Raw screencast workers needed explicit global lifecycle registration so forced runtime shutdown drains sockets even if a caller skips normal workspace cleanup.
13. Continuous mode could be overwritten by a synchronous fallback snapshot between animation frames, making receipts misstate the authoritative frame source. Continuous streams now retain their last live frame until a newer live frame arrives.
14. Browser/runtime transport fallback is now explicit (`cdp-websocket-live` → `cdp-screencast-cooperative` → `snapshot-fallback`) rather than silently presenting different assurance levels under one label.

Pixels remain observer-only; semantic/runtime evidence still governs verification.

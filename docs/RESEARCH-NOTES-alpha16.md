# Research Notes — alpha.16 continuous viewport and forensic pass

The main design constraint was thread affinity. Playwright sync objects remain owned by their original thread. Continuous frames therefore use a separate raw CDP WebSocket after the page target ID is obtained and the temporary Playwright CDP identity session is detached. The worker publishes only immutable PNG artifacts + metadata under a per-session lock.

Forensic findings fixed in this pass include: literal NUL bytes in the Observatory JavaScript source; cross-session frame-sequence invalidation; non-injective session filename sanitization; live-pixel retention after close/crash; sensitive password values leaking through ARIA; sensitive value length leaking through typing receipts; JSON-style console secrets and inline-handler source leaks; credential-bearing public URL/target leakage; possible torn stream metadata; and the new DevTools loopback port being reachable by the project's permissive localhost route unless explicitly denied.

The continuous-stream admission test deliberately sleeps the owning Python/Playwright thread while an animated page changes. `stream_seq` must still advance. This distinguishes a genuinely independent transport from a cooperative callback loop.

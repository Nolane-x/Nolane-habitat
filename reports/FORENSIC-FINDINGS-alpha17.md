# Alpha.17 Forensic Findings — stability/completion pass

Scope was intentionally constrained: no new subsystem. The pass searched for small correctness, lifecycle, portability, observability and release-state defects inside existing Habitat areas.

## Findings corrected

1. **Runtime UI handle collision / project spoofing.** Duplicate DOM `id`/`data-testid` values could map to the same semantic handle, while project markup could pre-populate Habitat's handle attribute. Habitat now owns a page-local WeakMap identity allocator, overwrites project-provided handle attributes, suffixes duplicates and encodes selector-unsafe characters.
2. **Noisy-page observer memory growth.** Console/network events could accumulate without a hard bound between observations. Buffers are now bounded and expose explicit dropped-event counts instead of silently pretending the tail is complete.
3. **Observer frame metadata race.** Frame path/sequence/source/stream metadata could be sampled across two publication moments. The public frame tuple is now read under the same frame lock used by publishers.
4. **Browser-open cleanup gap.** Browser context/page creation occurred partly before the cleanup boundary. Invalid viewport inputs now fail before browser side effects and partial context creation is cleanup-owned.
5. **Weak UI assertion validation.** Invalid count/exists combinations or non-string action values could reach deeper runtime semantics. The protocol/runtime now rejects malformed inputs early and supports explicit `exists=false` absence assertions.
6. **Observatory operator projection starvation.** Reconstructing the active browser from only the generic recent activity window could lose UI state on projects with heavy non-UI activity. A dedicated bounded UI-event projection plus direct open-receipt recovery now preserves the active session without making the generic timeline unbounded.
7. **Stream generation stale-state carryover.** Monotonic frame counters could be compared across different stream epochs and preserve an old generation's high sequence. Epoch changes now reset generation-local counters and invalidated animation state.
8. **Observatory IPv6 contract mismatch.** `::1` was accepted by the CLI while the default HTTP server remained IPv4 and URLs were not bracketed. Observatory now selects an IPv6 server and emits valid `http://[::1]:PORT/` loopback URLs.
9. **SQLite read-only URI portability.** Observatory built the read-only SQLite URI by quoting a filesystem string manually. It now derives the URI from `Path.as_uri()`, preserving Windows drive/path semantics.
10. **Transport polling mismatch.** The spectator frontend polled at near-live cadence even when the browser transport had fallen back to a slower snapshot mode. It now honors the runtime `poll_hint_ms` within bounded limits.
11. **Atomic-write same-process collision.** The source-authority primitive used a PID-derived temp path, allowing writers in one process to collide. It now uses a unique same-directory temporary file so final replacement stays on the destination filesystem.
12. **Atomic-write fd reuse/double-close race.** A late stress rerun exposed `OSError(9, 'Bad file descriptor')`: the temporary-file descriptor variable was reused for directory fsync, then could be closed a second time after the OS reassigned that number to another thread. Temp-file and directory descriptor ownership are now separate; 100 rounds × 32 concurrent writers passed after the fix.
13. **Continuous-stream test over-constrained the live head.** Alpha.16 expected the latest live frame sequence to equal an action-boundary receipt. A continuous stream may legitimately advance after the receipt. The test now requires the live head to be at least that sequence and verifies the exact action-boundary frame through the bounded ring.
14. **Release/document/test drift.** Installation/protocol documentation and one historical release-identity assertion were stale, and the default matrix shard name omitted alpha.17 tests. Current docs/version assertions/matrix membership are synchronized; historical release references remain explicitly historical.

## Claim boundary

Alpha.17 is a completion/stability release over existing Browser/AI Operator, Observatory, Workspace/SourceAuthority, protocol and release tooling. It does not add an OS remote desktop, new agent architecture, new model layer or new execution substrate. Pixel frames remain observer-only; semantic/runtime verification remains authoritative.

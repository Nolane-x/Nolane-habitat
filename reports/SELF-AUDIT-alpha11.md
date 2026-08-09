# Self Audit — Nolane Habitat 0.1.0-alpha.11

## Admission stance

Alpha.11 is admitted as an **agent-underlay + realtime cognitive observatory** checkpoint, not as a completed universal semantic/runtime platform.

## Preserved failure / correction ledger

### F1 — Observatory cross-thread SQLite failure
**Observation:** real threaded `/api/snapshot` raised `sqlite3.ProgrammingError` because the observer reused the Workspace connection created by the agent thread.  
**Rejected shortcut:** `check_same_thread=False` on the authoritative connection.  
**Correction:** `ObservatoryReadModel` opens short-lived `mode=ro`, `PRAGMA query_only=ON` connections per observer request.  
**Verifier:** real HTTP test plus `ResourceWarning`-as-error run.

### F2 — MCP attach tool would grow the compact catalog
**Observation:** a separate stateless identity attach tool would make 13 MCP tools and reintroduce tool-selection/context overhead.  
**Correction:** `habitat_start_task` mints an explicit `agent_id` and returns it for stateless follow-up requests; catalog remains 12.

### F3 — Initial Observatory snapshot had no recent activity history
**Observation:** an Observatory opened mid-task showed only future SSE events.  
**Correction:** bounded recent activity replay is included in the initial snapshot; SSE resumes from monotonic sequence.

### F4 — Project Memory recall privacy surface
**Observation:** the first store query shape was broad enough that agent-scoped recall could have included another agent's private memories.  
**Correction:** Workspace recall filters private records to the requesting agent while shared memories remain visible to all agents.  
**Verifier:** Agent A/B recall regression.

### F5 — AGI stress harness API drift
**Observation:** alpha.11 harness passed `agent_id` to `context_fetch_pages`, which derives attribution from the context handle and does not accept that argument.  
**Correction:** harness follows the Workspace contract; failed run was not reused as evidence.

### F6 — Chromium direct loopback navigation blocked by release environment policy
**Observation:** Playwright/Chromium may return `ERR_BLOCKED_BY_ADMINISTRATOR` for direct loopback navigation.  
**Correction:** benchmark fetches the real live HTTP snapshot first; when navigation is blocked, the exact live payload is rendered through the same packaged HTML/CSS/JS with a local fetch/EventSource shim. No mock task/state is substituted.  
**Boundary:** this proves renderer/data integration, not that every managed browser policy permits localhost navigation.

### F7 — Combined regression-matrix invocation timed out externally
**Observation:** a combined matrix command was cut before emitting a report.  
**Correction:** four exhaustive bounded process shards were run independently.  
**Evidence:** 66 + 38 + 68 + 26 = 198 tests PASS, 0 shard failure/timeout/infra-error.  
**Boundary:** combined timeout is not relabeled PASS or FAIL.

## Open technical frontiers

- Tree-sitter/LSP/SCIP are capability-discovered, not universally active Habitat providers.
- Runtime Twin is not a complete OTLP collector, profiler, distributed tracer, or debugger lifecycle manager.
- Runtime source linkage is provenance evidence, not causal inference.
- Observatory graph is bounded and can require level-of-detail/aggregation for very large live worlds.
- Remote observer exposure/authentication is intentionally absent; server is loopback-only.
- Production hostile-code sandbox remains provider/host dependent.
- Project Memory retention/privacy/encryption requires further enterprise hardening.
- Framework-complete UI program cognition remains open.
- Same-model Habitat-vs-filesystem product-quality A/B remains unrun.

## Claim boundary

Alpha.11 can make an external agent's environment more machine-native and cognition-friendly. It does not make a model an AGI by itself, does not expose private chain-of-thought, and does not prove coding-success uplift.

### F8 — RC two-shard command externally cut after first completed shard
**Observation:** a release-tool invocation containing two sequential shard runs was cut after alpha0–4 had already passed; alpha5–7 did not emit a result.  
**Correction:** the unfinished shard and the remaining shards were run independently from the same clean RC.  
**Admission:** 198/198 clean-RC tests passed across completed independent shards. The cut command itself is not counted.

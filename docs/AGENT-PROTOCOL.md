# Habitat Agent Protocol — current surface (0.1.0-alpha.17)

The stable wire envelope remains `habitat.agent.v1alpha2` for backward compatibility. Current high-level additions include the durable Executive Trajectory (`workspace.executive.*`), read-only Observatory controls, epistemic/project memory/runtime surfaces, and semantic browser operations under `ui.runtime.*`.

The Observatory is not part of the mutation control plane. Its HTTP surface remains spectator-only. MCP remains a compact 12-tool adapter; the internal protocol below is canonical. Runtime UI handles are session-local identities, invalid viewport/action value types fail before Playwright action semantics, and UI assertions may express explicit absence with `exists=false`.

## Stable wire envelope — `habitat.agent.v1alpha2`

Release version and protocol generation remain intentionally separate. Alpha.17 is a compatible method expansion/hardening release and does not force a transport rename.

NDJSON transport is provided by `habitat.server`:

```json
{"id":1,"method":"workspace.orient","params":{"task":"fix login validation","budget":12}}
```

There is no generic `shell.exec`.

## Line-budget semantic exploration

- `workspace.explore(task,line_budget,max_regions,context_budget)`

Returns ranked symbol/diagnostic regions with path + line bounds + trust while reading zero exact source bytes. Low-confidence/no-gold exploration abstains. The returned context handle can then be handed to Context VM page planning/faulting.

## Task orientation / calibrated retrieval

- `workspace.enter`
- `workspace.orient(task,budget)`
- `workspace.context.page(handle,offset,limit)`
- `workspace.context.refresh(handle,budget)`
- `workspace.context.materialize(handle,max_source_bytes,max_objects)`

Orientation returns task objects plus a `decision_packet` containing retrieval confidence, concept coverage and an abstention recommendation. Context metadata is orientation evidence, not source authority.

## Virtual context memory

- `workspace.context.address_space(handle,max_pages)`
- `workspace.context.fetch(handle,page_ids,max_source_bytes)`
- `workspace.context.prefetch(handle,max_source_bytes,max_pages)`
- `workspace.context.plan_next(handle,fetched_page_ids,max_pages,max_estimated_bytes)`
- `workspace.context.feedback(handle,used_object_ids,unhelpful_object_ids,weight)`
- `workspace.context.efficiency(handle)`

Context handles are immutable/revision-bound. Virtual pages hold metadata pointers. Exact symbol/diagnostic source faults in only after revision/digest validation and byte-budget admission. File objects are metadata-only pages by default.

## Persistent Context Residency

- `workspace.context.residency.configure(max_objects,max_source_bytes)`
- `workspace.context.residency.admit(handle,pin_top,max_admit)`
- `workspace.context.residency.status`
- `workspace.context.residency.materialize(max_source_bytes,max_objects)`
- `workspace.context.residency.touch(object_ids)`
- `workspace.context.residency.pin(object_ids,pinned)`
- `workspace.context.residency.evict(object_ids,stale_only)`

Residency stores object/provenance state, not copied source bodies. Stale residents never become current exact-source evidence.

## Query / inspection / references

- `workspace.query(query,limit)`
- `workspace.inspect(object_id,include_source)`
- `workspace.inspect.batch(object_ids,include_source,max_objects)`
- `workspace.references(object_id,limit)`
- `workspace.impact(changed_paths,object_ids,max_depth)`
- `workspace.source.read(path,start_line,max_lines)`
- `workspace.evidence.active(kind,limit)`

Active runtime/verification evidence is first-class. Resolved evidence remains auditable but is suppressed from live lexical task retrieval.

## Content-addressed project state

- `workspace.state.merkle(revision_id,prefix)`
- `workspace.state.merkle.diff(from_revision,to_revision,prefix)`

Merkle state is derived from already-computed file digests and reads zero additional project source bytes.

## Backend identity / source authority

- `workspace.backend.info`

The Semantic Twin is derived. The current release binds canonical `SourceAuthority` and `ExecutionProvider` independently beneath the compatibility ProjectBackend. Execution receipts expose both identities; local and directory-mirror authorities share the same cognitive protocol.

## Live synchronization

- `workspace.refresh(reason)`
- `workspace.watch.start(interval_s)`
- `workspace.watch.poll(limit)`
- `workspace.watch.wait(timeout_s,limit)`
- `workspace.watch.status`
- `workspace.watch.stop`
- `workspace.events.poll(since_seq,limit,reconcile)`
- `workspace.diff.since(revision_id)`

Watcher metadata is an accelerator. Deep content hashing remains the consequential mutation integrity boundary.

## Transactional mutation

- `workspace.change.stage(operations)`
- `workspace.change.stage_symbol(symbol_id,new_source)`
- `workspace.change.stage_rename_symbol(symbol_id,new_name)`
- `workspace.change.commit(transaction_id)`
- `workspace.change.rollback(transaction_id)`

`stage_rename_symbol` is currently a fail-closed Python/Jedi precision lane. It emits exact identifier-span edits rather than global text replacement.

## Verification / execution

- `workspace.verification.plan(changed_paths,object_ids)`
- `workspace.verification.run(changed_paths,object_ids,timeout_s)`
- `action.run(capability,timeout_s)`

Execution produces typed receipts. Test failures may become active evidence objects. Raw stdout/stderr remain fallback evidence, not the primary control surface.

## Checkpoint / resume

- `workspace.checkpoint(task,resident_object_ids,notes,next_action,episode_id)`
- `workspace.resume(session_id)`

Checkpoint binds revision/root/Merkle/provider/backend/event/residency state and may bind an active work episode. Resume chooses `direct`, `selective-revalidate` or `reorient` instead of trusting narrative state alone.

## Work episodes / workflow causality

- `workspace.episode.start(task,context_handle)`
- `workspace.episode.status(episode_id)`
- `workspace.episode.finish(episode_id,status,outcome)`
- `workspace.causality.explain(ref_id)`
- `workspace.causality.graph(ref_id,max_depth,max_edges)`
- `workspace.episode.efficiency(episode_id)`

Episodes link context, staged/committed transactions, revisions, verification receipts, checkpoints and outcomes. This is workflow provenance rather than a claim of complete program causality.

## Protocol trace instrumentation

- `workspace.trace.start(label)`
- `workspace.trace.status(trace_id)`
- `workspace.trace.stop(trace_id)`

Trace sessions record calls, durations, serialized request/response bytes and exact-source bytes. They are instrumentation, not token counts or reasoning metrics. Trace failure may not alter the underlying operation result.

## UI

- `ui.observe(path)`
- `ui.runtime.open(target,screenshot,viewport)`
- `ui.runtime.observe(session_id,screenshot)`
- `ui.runtime.act(session_id,action,handle,value,screenshot)`
- `ui.runtime.assert(session_id,assertions)`
- `ui.runtime.close(session_id)`

`ui.runtime.assert` evaluates DOM/accessibility/runtime state and explicitly reports whether pixels were consulted.

## Semantic provider report

`workspace.semantic.providers` reports provider availability, version/scope and partition/cache metrics where available. Missing LSP/SCIP/Tree-sitter lanes remain explicit capability gaps.

## MCP adapter

The internal protocol above remains canonical. `habitat-mcp-server` optionally composes it into a compact 12-tool MCP surface targeting the 2026-07-28 specification line. The adapter intentionally exposes high-level loops rather than every internal primitive.

## Error behavior

Unknown methods fail typed. Invalid parameters fail before side effects. Stale context/mutation state fails closed. Unsupported semantic rename fails rather than silently degrading to search/replace. Arbitrary command strings are not accepted as a generic shell channel.

# Public compatibility policy

`habitat.agent.v1alpha2` is a versioned public protocol surface. The compact MCP catalog, MCP spec target, protocol version, and full protocol method set are frozen by `tests/fixtures/contracts/agent-v1alpha2.json`.

`python tools\verify_contracts.py` compares the checked-out public surface with that fixture and writes a commit-bound report. A difference is a breaking candidate until the protocol version, fixture, migration guidance, and release evidence are reviewed together. Updating the fixture is therefore a compatibility decision, not a formatting change.

The verifier does not modify a workspace or start an MCP server. Its CI report is required for alpha admission, alongside recovery, fault, scanner, artifact, and review evidence.

## Transport boundary

The stdio adapter accepts one strict JSON object per NDJSON line, up to 256 KiB. Duplicate object keys, `NaN`/`Infinity`, unpaired Unicode surrogates, and non-object requests are rejected before protocol dispatch. Rejections use stable typed envelopes (`INVALID_JSON`, `INVALID_REQUEST`, or `REQUEST_TOO_LARGE`) and do not expose parser exceptions or filesystem paths. These invalid forms are outside the supported request contract; valid `habitat.agent.v1alpha2` requests retain their existing response shape.

The documented read-only protocol methods do not create activity or trace telemetry merely because they were observed. `workspace.source.read` reads the indexed source snapshot without triggering an implicit workspace reconcile; callers that require a fresh semantic revision must invoke the explicit `workspace.refresh` operation first. The compact MCP `habitat_inspect` and `habitat_references` tools similarly project the current indexed snapshot without creating agent observations or activity; callers needing freshness or agent-memory recording use the explicit workspace operations. If the source fingerprint changes during a range read, Habitat fails closed and reports a conflict rather than silently serving bytes from a newer world state.

The loopback Observatory's `GET /api/health`, `GET /api/snapshot`, and `GET /api/activity` endpoints are also state-neutral projections. They open short-lived read-only SQLite connections and must not reconcile source state, emit activity, mutate task/agent state, or share the control-plane connection. Freshness remains explicit through the normal workspace operations; a viewer cannot make the workspace current merely by opening the Observatory.

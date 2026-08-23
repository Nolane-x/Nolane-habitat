# Capability matrix

Habitat reports effective authority and execution properties from the workspace's active backend. The report is available through `habitat capabilities <workspace>` and in the `enter` response as `capability_report`.

| Provider profile | Sandbox | Network restricted | Filesystem restricted | Process isolated | Interpretation |
| --- | --- | --- | --- | --- | --- |
| `trusted-local-process` | No | No | No | No | Normal local execution; use only under the user's local authority. |
| `verified-sandbox` | Yes | Yes | Yes | Yes | Reported only when the execution provider includes full sandbox, network confinement, filesystem confinement, and PID namespace evidence. |

The capability gate fails closed: a workflow calling `require_capability(..., "sandboxed")` receives `PermissionError` unless that capability is currently verified. Availability of a test/build command is separate from execution containment and must not be interpreted as sandboxing.

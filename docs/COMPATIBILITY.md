# Public compatibility policy

`habitat.agent.v1alpha2` is a versioned public protocol surface. The compact MCP catalog, MCP spec target, protocol version, and full protocol method set are frozen by `tests/fixtures/contracts/agent-v1alpha2.json`.

`python tools\verify_contracts.py` compares the checked-out public surface with that fixture and writes a commit-bound report. A difference is a breaking candidate until the protocol version, fixture, migration guidance, and release evidence are reviewed together. Updating the fixture is therefore a compatibility decision, not a formatting change.

The verifier does not modify a workspace or start an MCP server. Its CI report is required for alpha admission, alongside recovery, fault, scanner, artifact, and review evidence.

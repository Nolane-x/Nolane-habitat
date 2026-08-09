# Alpha.9 Frontier Disposition in Alpha.10

| Alpha.9 frontier | Alpha.10 disposition | Boundary |
|---|---|---|
| Filesystem-confined hostile-code sandbox | **PARTIAL/PROVIDERIZED**: Bubblewrap provider + executable probe + fail-closed untrusted policy | Not admitted on this host; caller policy/kernel still matter |
| Distributed multi-agent coordination | **PARTIAL**: read-set invalidation, selective revalidation, leases, owner binding, disjoint optimistic rebase | Local workspace coordination, not distributed consensus/merge |
| Temporal/dependency world | **ADVANCED**: branches/worktrees/conflicts/commit impact + lock-aware direct dependencies | Not complete runtime/transitive world |
| Private cognition | **ADVANCED**: private residency/utility/read-set/beliefs + host-side forget | Shared verified world remains common |
| Governance | **ADVANCED**: path-scoped preflight/approval + policy before side effects | Approval grant is host control, not autonomous agent capability |
| Retention/security | **PARTIAL**: bounded GC/retention + permission hardening + secret redaction | No encryption at rest |
| Same-model A/B | **INFRASTRUCTURE READY**: comparability gate + independent evaluator contract | No real external model result yet |
| Workspace coupling | **PARTIAL**: service/provider boundaries continue to grow | HabitatWorkspace is still a coordination center |

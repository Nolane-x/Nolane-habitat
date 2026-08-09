# Alpha.9 Research Notes

Alpha.9 follows the alpha.8 external-audit disposition rather than broadening the product indiscriminately. The highest-value open issues selected for this checkpoint were: formal policy, unsafe execution posture, per-agent memory isolation, multi-agent write coordination, Git/dependency temporal context, uncertainty correlation and the missing same-model A/B mechanism.

A key design rejection is **"network namespace = sandbox"**. The local Linux host can create user/network namespaces, so Habitat can deny external network and impose resource limits. It still sees host filesystem paths. Alpha.9 therefore calls the profile `network-contained`, reports `filesystem_restricted=false`, and refuses to satisfy `untrusted` policy with it.

A second rejection is **"more evidence rows = more confidence"**. Hypothesis assessment groups evidence by source/provider so correlated repeated receipts get diminishing returns. This is still heuristic, not calibrated probability.

A third rejection is **"multi-agent = share the same DB"**. Alpha.9 creates agent sessions, per-agent context utility and path leases. Verified world/evidence remains shared. This is a minimal architectural split, not a distributed agent-team runtime.

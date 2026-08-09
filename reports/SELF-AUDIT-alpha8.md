# Self Audit — 0.1.0-alpha.8

## Failures kept visible

1. **Alpha.7 manifest schema regression:** alpha.8 writer emits schema 5 while a historical test locked exact schema 4. Correction: readers/schema accept 4 and 5; old field semantics are preserved; historical test checks compatibility rather than freezing the writer version.
2. **Context efficiency schema drift:** alpha.8 added authority I/O fields but alpha.7 schema rejected them. Correction: additive optional fields preserve old documents while allowing honest new accounting.
3. **Windows perception assumption:** POSIX ctime/inode is not a portable Windows change-time oracle. Correction: Windows ordinary reconcile deep-verifies content until a native change journal exists; performance tradeoff is explicit.
4. **Full-discovery wall-clock:** one monolithic unittest invocation can hit the external runner timeout despite individual shards being green. Correction: release gate records full attempt plus exhaustive shards; timeout is not labeled PASS.
5. **Warm deep refresh economics:** AGI corpus deep `refresh()` still hashes the whole source corpus. Correction: deep refresh is explicitly a scrub, not the ordinary cognitive path; mutation uses reconcile + digest-bound target + targeted post-write refresh.
6. **Execution safety remains partial:** output/network accounting improvements do not create an OS sandbox. Release docs call hostile-repo execution a production blocker.

## Admission principle
A mechanism is admitted only with executable regression and an honest claim boundary. Partial mitigations remain OPEN in `ALPHA6-AUDIT-DISPOSITION-alpha8.md`.

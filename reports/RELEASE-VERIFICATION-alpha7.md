# Nolane Habitat 0.1.0-alpha.7 — Release Verification

## Source-tree gates
- full unittest discovery: 130 / 130 PASS in a successful normal-exit run;
- compileall: PASS;
- JSON schemas parse: PASS;
- `habitat.__version__`: `0.1.0-alpha.7`;
- VERSION: `0.1.0-alpha.7`;
- pyproject package version: `0.1.0a7`;
- README quick-start `create -> enter -> orient`: PASS, high-confidence credential fixture;
- alpha.7 end-to-end demo: PASS;
- backend composition/equivalence: PASS;
- 202-file line-budget explorer: PASS;
- supplied AGI-ZIP stress: PASS.

## Empirical bounded results
- distractor credential: 3 selected lines, 127 exact-source bytes faulted, 0 noise regions;
- distractor billing: 3 selected lines, 92 exact-source bytes faulted, 0 noise regions;
- no-gold: low confidence, abstain, 0 source bytes;
- supplied AGI corpus: 251 files, 865 symbols, 4,372 occurrences;
- AGI warm refresh: 0 files compiled, 251 reused;
- Python/Jedi warm partitions: 78 reused, 0 recomputed.

These values are deterministic plumbing evidence. Bytes/lines are not tokens and do not establish model success.

## Packaging gate
This document is written before final packaging. The final ZIP must additionally pass independent manifest/hash verification, clean extraction tests, empirical verifier reruns, quick-start and isolated package import. External final ZIP SHA-256 is reported at delivery time because embedding it here would change the archive itself.

## Independent RC gate
Artifact checked: `Nolane-Habitat-0.1.0-alpha.7-RC.zip`.

- ZIP integrity: PASS;
- independent manifest verification: 217 listed entries, 0 missing, 0 extra, 0 hash mismatch, root hash PASS;
- clean extraction test coverage: all test modules PASS (64-test first shard plus independently executed remaining modules; no assertion/error failures);
- clean alpha.7 demo: PASS;
- clean backend composition/equivalence: PASS;
- clean 202-file explorer benchmark: PASS;
- clean supplied AGI-ZIP stress: PASS;
- clean quick-start: PASS / high confidence;
- isolated `pip --target` import from `/tmp`: PASS, `0.1.0-alpha.7` loaded from the target directory;
- missing optional MCP SDK path: clear typed RuntimeError PASS.

A full-discovery clean-RC invocation also showed external-runner latency variance and was not counted as a PASS when cut off. This is retained in `SELF-AUDIT-alpha7.md`; module/shard gates were used to obtain complete clean-artifact test coverage without converting timeout into evidence.

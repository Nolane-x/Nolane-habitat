# Release Verification — 0.1.0-alpha.3

## Candidate verified

Candidate archive: `Nolane-Habitat-0.1.0-alpha.3-RC.zip`

Candidate external SHA-256 at verification time:

`07e8f5abafb64bccacc5dd6170196cea888b190f9f39f1a0603e907b4c6dc55a`

The final delivery is rebuilt after adding this report, so its external SHA-256 is intentionally published outside the archive after final-artifact verification rather than embedded recursively here.

## Independent artifact gates

The candidate was extracted into a clean directory and checked without trusting the packager's own success message.

- ZIP integrity: **PASS** (`unzip -t`, no errors).
- Manifest version: **0.1.0-alpha.3**.
- Manifest entries excluding manifest: **115** at RC stage.
- Missing listed files: **0**.
- Unlisted files: **0**.
- Size/SHA-256 mismatches: **0**.
- Recomputed manifest root hash: **PASS**.
- Clean-extracted unit/adversarial suite: **71/71 PASS**.
- Clean-extracted alpha.3 demo: **PASS**.
- Clean-extracted supplied-AGI-ZIP stress probe: **PASS**.
- Clean-extracted navigation-plumbing harness: **PASS**; both arms found all three fixture targets.
- README command contract (`create → enter → orient`) from clean extraction: **PASS**.
- Isolated package target import/version: **PASS**, `0.1.0-alpha.3`.

## Demo observations from clean candidate

- Context Materializer: 361 exact-source bytes, 6 objects in the fixture run.
- Targeted verification receipt exit code: 0.
- Runtime UI output: `Hello Nolane` on the release host.
- Warm demo refresh: 0 compiled / 9 reused.

## Supplied AGI-ZIP stress observations from clean candidate

- files: 251;
- symbols: 865;
- occurrences: 3,429;
- warm refresh: 0 compiled / 251 reused;
- no-op graph persistence: 2,918 relation rows unchanged, 3,429 occurrence rows unchanged, zero insert/update/delete;
- documentation-only targeted edit: provider domains reused;
- Python targeted edit: base semantic domain invalidated while TypeScript domain remained reusable.

These values are engineering observations on that corpus, not model-intelligence measurements.

## Package-install environment note

The first isolated `pip install` attempt used default PEP 517 build isolation and tried to fetch `setuptools>=68` from an unavailable package index. This gate was **not** counted as pass. The host already contained setuptools 82.0.1, satisfying the declared requirement, so the smoke was rerun with `--no-build-isolation --no-deps`; installation and isolated import/version then passed. The event is preserved in `SELF-AUDIT-alpha3.md`.

## Claim boundary

Release admission verifies the packaged implementation and included bounded mechanisms. It does not establish universal code understanding, reduced LLM token usage, coding-success uplift, AGI capability, production hostile-code isolation, or framework-complete UI ownership.

## Final artifact rule

After this verification report is inserted, the delivery must be rebuilt, independently manifest-verified again, and the clean-extracted test/demo/stress gates rerun on the **final** ZIP. The final external SHA-256 is reported to the user only after those gates pass.

# Release Verification — 0.1.0-alpha.2

Date: 2026-08-07
Verification target: packaged release candidate extracted into a clean directory
Candidate SHA-256: `f4ca51b42ab798810b8df8ead594d2071e6a959628da31b33d3cd5953c3b7642`

This report records the **independent release-candidate gate**. The final delivery is repackaged after adding this report, so its final archive SHA-256 is intentionally verified externally after packaging to avoid a self-referential archive hash.

## Gate results

- ZIP structural integrity: PASS (`unzip -t`, no errors).
- Manifest verification: PASS.
  - listed files: 95 (manifest excluded by format);
  - missing listed files: 0;
  - unlisted delivery files: 0;
  - SHA-256/size mismatches: 0.
- Clean extracted test suite: **57/57 PASS**.
- Clean extracted alpha.2 vertical demo: PASS.
  - targeted verification exit code: 0;
  - runtime UI result: `Hello Nolane`;
  - warm refresh: 0 compiled / 7 reused / project-semantic cache hit.
- Clean extracted supplied-AGI-ZIP stress: PASS.
  - corpus: 251 files / 865 symbols / 3429 occurrences;
  - warm refresh: 0 compiled / 251 reused / project-semantic cache hit;
  - one-file external edit: 1 compiled / 250 reused.
- Package installation smoke (`pip --no-build-isolation --no-deps --target`): PASS.
- Installed import reports version: `0.1.0-alpha.2`.

## Admission boundary

These gates establish artifact integrity and the bounded implementation behaviors represented by the included tests/demos. They do not establish universal model token reduction, universal task success, AGI capability, hostile-code sandboxing, or unsupported-language semantic precision.

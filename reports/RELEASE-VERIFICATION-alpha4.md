# Release Verification — 0.1.0-alpha.4

Date: 2026-08-07

RC archive: `Nolane-Habitat-0.1.0-alpha.4-RC.zip`

## Independent RC verification

- ZIP integrity: **PASS** (`unzip -t`, no compressed-data errors).
- Manifest version: **0.1.0-alpha.4**.
- Manifest entries excluding manifest: **133**.
- Independent missing files: **0**.
- Independent unlisted files: **0**.
- Independent size/SHA-256 mismatches: **0**.
- Independent root hash recomputation: **PASS**.
- Clean-extracted compileall: **PASS**.
- Clean-extracted test suite: **88/88 PASS**.
- Clean-extracted alpha.4 demo: **PASS**.
- Clean-extracted supplied-AGI-ZIP stress: **PASS**.
- Clean-extracted alpha.4 protocol trace benchmark: **PASS**.
- README CLI quick-start `create → enter → orient`: **PASS**.
- Host-backend isolated-target package install/import: **PASS**, `habitat.__version__ == 0.1.0-alpha.4`.

RC SHA-256 before adding this final report:

`280aa6fa289eece27c32f527d0ee41740669998392a345d5feb0df0c098db638`

## Evidence assertions rechecked from clean extraction

- Demo targeted verification exit code: **0**.
- Demo runtime UI handler evidence exists when browser capability is available.
- AGI stress warm refresh: **0 compiled / 251 reused**.
- AGI stress warm base relation partitions: **0 recomputed**.
- AGI stress documentation edit: **1 file compiled / 0 base relation partitions recomputed**.
- AGI stress body-only Python probe: **1 file compiled / 0 base relation partitions recomputed**.
- Trace benchmark credential paths after retrieval correction: only `auth.py` semantic/file objects.
- Trace benchmark unrelated billing paths: only `billing.py` semantic/file objects.

## Packaging environment note

A first package smoke inside a newly-created stdlib venv failed because that venv did not expose the host `/opt/pyvenv` setuptools backend. The package requirement was **not** weakened. The admitted package smoke used the host's verified `setuptools 82.0.1` backend with `--no-build-isolation --no-deps --target`, then imported Habitat in Python isolated mode from only that target path. This finding is preserved in `SELF-AUDIT-alpha4.md`.

## Claim boundary

This release verification admits artifact integrity and the bounded alpha.4 mechanisms only. It does not convert protocol bytes into token claims, stress-corpus results into AGI evidence, static UI correlations into universal runtime provenance, or local typed execution into hostile-code sandboxing.

A final delivery ZIP is rebuilt after this report is included; its manifest/hash must therefore be independently verified again before handoff.

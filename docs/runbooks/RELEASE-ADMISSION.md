# Release admission

`tools/promote_release.py` evaluates a supplied release manifest and writes a machine-readable verdict. It never creates a Git tag, publishes a package, uploads an artifact, or creates a GitHub release.

For an alpha candidate, the gate requires hash-bound `truth-core`, `matrix`, `faults`, `artifacts`, `scanner`, `db-recovery`, and `contract` reports, at least one artifact, and at least one review record. Every required report must contain a verified payload hash, `status: passed`, and the same 40-character commit SHA as the manifest. Distribution evidence includes a deterministic member manifest and rejects unsafe paths, `.env` files, private-key extensions, local databases, Habitat state, and Python bytecode caches. The review record is hashed by the builder; its digest must not be reused from any report or artifact. This is a binding check, not a claim that a filename proves reviewer identity—follow the independent-review procedure before supplying the record.

## CI scanner evidence

CI runs the GitHub Actions Semgrep policy before its local quality gate. The scanner report is valid only for the exact Git commit it names: the gate rejects a missing report, a scanner identity mismatch, a non-passing status, findings, errors, a digest mismatch, or a different commit.

To reproduce that check for the checked-out candidate:

```powershell
$commit = git rev-parse HEAD
python tools\check_release_identity.py --source-commit $commit --out .test-artifacts\identity.json
python tools\run_test_matrix.py --mode shard --workers 1 --timeout 600 --source-commit $commit --out .test-artifacts\matrix.json
python tools\run_semgrep.py --source-commit $commit --out .test-artifacts\semgrep-workflows.json
python tools\quality_gate.py --identity .test-artifacts\identity.json --matrix .test-artifacts\matrix.json `
  --scanner semgrep=.test-artifacts\semgrep-workflows.json --require-scanner semgrep `
  --expected-commit $commit --out .test-artifacts\truth-core.json
```

The scanner report is CI evidence, not a release-admission verdict by itself. Release admission still requires the complete manifest and independent review described below.

Generate the SQLite recovery and fault-injection reports from the same checked-out candidate. These commands use temporary fixtures only and do not open or modify a user workspace:

```powershell
python tools\run_db_recovery_suite.py --source-commit $commit --out .test-artifacts\db-recovery.json
python tools\run_reliability_suite.py --source-commit $commit --out .test-artifacts\faults.json
python tools\verify_contracts.py --source-commit $commit --fixture tests\fixtures\contracts\agent-v1alpha2.json --out .test-artifacts\contract.json
python -m build --no-isolation --outdir dist
python tools\verify_distribution.py --source-commit $commit --dist dist --out .test-artifacts\artifacts.json
```

Build the manifest from the actual evidence and artifact files; the builder computes the SHA-256 bindings rather than accepting manually entered values:

```powershell
$commit = git rev-parse HEAD
python tools\build_release_manifest.py --version 0.1.0-alpha.19 --commit $commit `
  --report truth-core=.test-artifacts\truth-core.json `
  --report matrix=.test-artifacts\matrix.json `
  --report faults=.test-artifacts\faults.json `
  --report artifacts=.test-artifacts\artifacts.json `
  --report scanner=.test-artifacts\semgrep-workflows.json `
  --report db-recovery=.test-artifacts\db-recovery.json `
  --report contract=.test-artifacts\contract.json `
  --artifact wheel=dist\nolane_habitat-0.1.0a19-py3-none-any.whl `
  --artifact sdist=dist\nolane_habitat-0.1.0a19.tar.gz `
  --review independent-review=reports\independent-review.json `
  --out dist\release-manifest.json
```

Evaluate the alpha gate and retain the verdict beside the other evidence:

```powershell
python tools\promote_release.py --manifest dist\release-manifest.json --target alpha-candidate --dry-run --out .test-artifacts\promotion-verdict.json
```

The command exits `0` only when every report required by the selected target has a valid digest and matching passed provenance, artifacts are present, and the review binding is valid; it exits `1` after writing a blocked verdict otherwise. A blocked verdict is evidence of a safe stop, not a publishing failure. External publication remains a separate, explicit action after the required evidence has been independently reviewed.

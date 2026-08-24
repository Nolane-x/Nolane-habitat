# Release admission

`tools/promote_release.py` evaluates a supplied release manifest and writes a machine-readable verdict. It never creates a Git tag, publishes a package, uploads an artifact, or creates a GitHub release.

For an alpha candidate, the gate requires hash-bound `truth-core`, `matrix`, `faults`, `artifacts`, `scanner`, `db-recovery`, `mutation-recovery`, `reproducible-build`, `protocol-conformance`, and `contract` reports, at least one artifact, and at least one separately named review or authorization record. Every report and review or authorization record must contain a verified payload hash, `status: passed`, and the same 40-character commit SHA as the manifest. The builder reads each evidence file once, records its file hash and parsed provenance from that same snapshot, then calculates `manifest_sha256` over canonical manifest JSON with that field omitted. A record supplied through `--review` additionally requires `schema: 1` and `evidence_type: "review"`; its canonical payload hash cannot equal a required report's. Its name identifies evidence only and does not establish reviewer identity or independent review. Dry-run promotion recalculates the manifest hash and writes a canonical, self-hashed verdict bound to that exact source commit and manifest hash; malformed manifests and invalid commits produce no verdict file. Distribution evidence includes a deterministic member manifest and rejects unsafe paths, `.env` files, private-key extensions, local databases, Habitat state, and Python bytecode caches. It also extracts the wheel `METADATA` and sdist `PKG-INFO`, checks their normalized project name and package version, and blocks if their canonical `Requires-Dist` inventories differ. The resulting `dependency_inventory_sha256` binds that inventory into the artifact report.

## Publication authorization

Alpha and other explicitly marked pre-releases may be published without an independent GitHub approval when the repository owner or a release maintainer explicitly authorizes that exact candidate. Owner authorization does not replace any technical evidence: every required report must pass, the artifacts and manifest must be bound to the candidate commit, the dry-run verdict must admit it, and no unresolved critical or high release finding may remain. A commit change invalidates the authorization and requires fresh commit-bound evidence.

Record this path as `maintainer-authorization` through `--review` and state the authorizing actor and basis in the record payload. Do not describe that record as an independent review. GitHub's prohibition on approving one's own pull request remains intact; this policy authorizes pre-release publication rather than manufacturing a GitHub approval.

Stable releases still require approval from a reviewer other than the change author, in addition to the complete technical evidence and an explicit publication action. If reviewer identity or independence cannot be established, the candidate remains eligible only for a clearly labelled pre-release.

## Reproducible-build evidence

CI resolves `HABITAT_SOURCE_COMMIT` to the pull-request head SHA for `pull_request` events and to the event SHA for push or manual events, then checks out that exact commit before producing evidence. It checks out the same candidate commit twice into distinct clean Git worktrees, then builds the wheel and sdist once in each copy with `SOURCE_DATE_EPOCH=0`. `normalize_sdist.py` rewrites only archive metadata that Setuptools leaves time-varying: gzip/tar timestamps, owner/group fields, and deterministic member order. It preserves every permitted entry's path, mode, and file bytes, and rejects links or other unsupported member types. `reproducible-build.json` blocks the alpha gate unless both worktrees are clean, both resolve to the candidate SHA, their hashed checkout identities differ, and both normalised artifact sets have the same SHA-256 values. The evidence records no absolute worktree paths. It proves repeatability across two clean copies in one CI OS/Python environment; it does not claim cross-environment, dependency-hermetic, or supply-chain reproducibility.

The local commands below use `python -m build --no-isolation`, matching CI. Run them from the documented development environment: install `setuptools>=68` and the `dev` extra first. Python 3.12+ virtual environments may not include `setuptools` automatically.

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

The scanner report is CI evidence, not a release-admission verdict by itself. Release admission still requires the complete manifest and the publication authorization appropriate to the release channel described above.

Generate the SQLite recovery and fault-injection reports from the same checked-out candidate. These commands use temporary fixtures only and do not open or modify a user workspace:

```powershell
python tools\run_db_recovery_suite.py --source-commit $commit --out .test-artifacts\db-recovery.json
python tools\run_mutation_recovery_suite.py --source-commit $commit --out .test-artifacts\mutation-recovery.json
python tools\run_reliability_suite.py --source-commit $commit --out .test-artifacts\faults.json
python tools\verify_contracts.py --source-commit $commit --fixture tests\fixtures\contracts\agent-v1alpha2.json --out .test-artifacts\contract.json
python tools\run_protocol_conformance_suite.py --source-commit $commit --out .test-artifacts\protocol-conformance.json
$env:SOURCE_DATE_EPOCH = "0"
$copies = Join-Path (Resolve-Path .test-artifacts) "reproducibility-copies"
$firstSource = Join-Path $copies "source-first"
$secondSource = Join-Path $copies "source-second"
$firstDist = Join-Path (Resolve-Path .test-artifacts) "dist-first"
$secondDist = Join-Path (Resolve-Path .test-artifacts) "dist-second"
New-Item -ItemType Directory -Force $copies | Out-Null
git clone --no-local . $firstSource
git clone --no-local . $secondSource
git -C $firstSource checkout --detach $commit
git -C $secondSource checkout --detach $commit
Push-Location $firstSource
python -m build --no-isolation --outdir $firstDist
Pop-Location
python tools\normalize_sdist.py --dist $firstDist --epoch 0
Push-Location $secondSource
python -m build --no-isolation --outdir $secondDist
Pop-Location
python tools\normalize_sdist.py --dist $secondDist --epoch 0
python tools\verify_reproducible_build.py --source-commit $commit `
  --first $firstDist --second $secondDist `
  --first-source $firstSource --second-source $secondSource `
  --out .test-artifacts\reproducible-build.json
python tools\verify_distribution.py --source-commit $commit --dist .test-artifacts\dist-first --out .test-artifacts\artifacts.json
```

Build the manifest from the actual evidence and artifact files; the builder computes the SHA-256 bindings rather than accepting manually entered values:

```powershell
$commit = git rev-parse HEAD
python tools\build_release_manifest.py --version 0.1.0-alpha.19 --commit $commit --target alpha-candidate `
  --report truth-core=.test-artifacts\truth-core.json `
  --report matrix=.test-artifacts\matrix.json `
  --report faults=.test-artifacts\faults.json `
  --report artifacts=.test-artifacts\artifacts.json `
  --report scanner=.test-artifacts\semgrep-workflows.json `
  --report db-recovery=.test-artifacts\db-recovery.json `
  --report mutation-recovery=.test-artifacts\mutation-recovery.json `
  --report reproducible-build=.test-artifacts\reproducible-build.json `
  --report protocol-conformance=.test-artifacts\protocol-conformance.json `
  --report contract=.test-artifacts\contract.json `
  --artifact wheel=.test-artifacts\dist-first\nolane_habitat-0.1.0a19-py3-none-any.whl `
  --artifact sdist=.test-artifacts\dist-first\nolane_habitat-0.1.0a19.tar.gz `
  --review maintainer-authorization=reports\maintainer-authorization.json `
  --out dist\release-manifest.json
```

Evaluate the alpha gate and retain the verdict beside the other evidence:

```powershell
python tools\promote_release.py --manifest dist\release-manifest.json --target alpha-candidate --dry-run --out .test-artifacts\promotion-verdict.json
```

The builder requires `--target` and writes no manifest unless the supplied evidence exactly matches that target and every report is valid, passed, and commit-bound. The dry-run command exits `0` only when it verifies that same contract, including the canonical manifest hash; it exits `1` after writing a blocked verdict otherwise. A blocked verdict is evidence of a safe stop, not a publishing failure. External publication remains a separate, explicit action. For a pre-release, a `maintainer-authorization` record documents the bounded owner/maintainer path above; it does not assert that an independent review occurred. Stable publication still requires actual independent approval.

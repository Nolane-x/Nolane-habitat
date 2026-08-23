# Release admission

`tools/promote_release.py` evaluates a supplied release manifest and writes a machine-readable verdict. It never creates a Git tag, publishes a package, uploads an artifact, or creates a GitHub release.

Build the manifest from the actual evidence and artifact files; the builder computes the SHA-256 bindings rather than accepting manually entered values:

```powershell
$commit = git rev-parse HEAD
python tools\build_release_manifest.py --version 0.1.0-alpha.19 --commit $commit `
  --report truth-core=.test-artifacts\truth-core.json `
  --report matrix=.test-artifacts\matrix.json `
  --report faults=.test-artifacts\faults.json `
  --report artifacts=.test-artifacts\artifacts.json `
  --artifact wheel=dist\nolane_habitat-0.1.0a19-py3-none-any.whl `
  --out dist\release-manifest.json
```

Evaluate the alpha gate and retain the verdict beside the other evidence:

```powershell
python tools\promote_release.py --manifest dist\release-manifest.json --target alpha-candidate --dry-run --out .test-artifacts\promotion-verdict.json
```

The command exits `0` only when every report required by the selected target is present and non-empty; it exits `1` after writing a blocked verdict otherwise. A blocked verdict is evidence of a safe stop, not a publishing failure. External publication remains a separate, explicit action after the required evidence has been independently reviewed.

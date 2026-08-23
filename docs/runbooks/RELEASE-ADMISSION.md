# Release admission

`tools/promote_release.py` evaluates a supplied release manifest and writes a machine-readable verdict. It never creates a Git tag, publishes a package, uploads an artifact, or creates a GitHub release.

Create a manifest whose report values and artifact hashes are content digests:

```json
{
  "version": "0.1.0-alpha.19",
  "commit": "<commit-sha>",
  "reports": {
    "truth-core": "<sha256>",
    "matrix": "<sha256>",
    "faults": "<sha256>",
    "artifacts": "<sha256>"
  },
  "artifact_hashes": {"wheel": "<sha256>"},
  "residual_risks": []
}
```

Evaluate the alpha gate and retain the verdict beside the other evidence:

```powershell
python tools\promote_release.py --manifest dist\release-manifest.json --target alpha-candidate --dry-run --out .test-artifacts\promotion-verdict.json
```

The command exits `0` only when every report required by the selected target is present and non-empty; it exits `1` after writing a blocked verdict otherwise. A blocked verdict is evidence of a safe stop, not a publishing failure. External publication remains a separate, explicit action after the required evidence has been independently reviewed.

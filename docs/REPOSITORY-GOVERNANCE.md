# Repository Governance

This document records repository-level enforcement separately from Habitat's in-repository release and verification logic. It is a current-truth surface, not evidence that GitHub administrator controls have been enabled.

## Current repository enforcement status

Observed on 2026-08-27 against `Nolane-x/Nolane-habitat`:

- `main` branch protection: **not enabled**.
- Required status checks on `main`: **not enforced by branch protection**.
- Repository rulesets: **none configured**.
- The repository does run **Habitat CI** and **Habitat CodeQL** workflows, but workflow success by itself is not the same as a repository rule that prevents an unverified update to `main`.

These statements describe the GitHub repository configuration observed at the date above. They must be re-checked through GitHub before being treated as current enforcement truth.

## What the repository already verifies in code

Habitat's CI currently binds release evidence to the pull-request head or pushed commit and exercises the supported Ubuntu/Windows and Python 3.10/3.14 matrix. The workflow covers release identity, the full regression suite, isolated regression evidence, public compatibility, protocol conformance, database and source-mutation recovery, fault injection, independent-checkout reproducible builds, distribution verification, Semgrep, and the local truth-core quality gate.

Foundation Convergence also collects `foundation-baseline.json` as descriptive evidence. That baseline is deliberately non-gating: timings and counts are observations from a particular runner and must not become superiority claims or release thresholds without a separately reviewed benchmark policy.

## Desired admin-enforced controls

The following controls are **recommended repository-administrator actions**. They are not claimed to be enabled by this document:

1. Require pull requests before updates to `main`; disable direct unreviewed pushes for ordinary development.
2. Require the relevant **Habitat CI** and **Habitat CodeQL** checks to pass on the exact pull-request head before merge.
3. Block force-pushes and branch deletion for `main`.
4. Require review for stable promotion. Preserve the explicitly documented owner-authorized prerelease path only where the release policy intentionally permits it; do not silently turn a prerelease exception into a stable-release exception.
5. Require conversations/review findings to be resolved before merge when that control fits the repository's collaboration model.
6. Keep GitHub Actions permissions least-privilege and keep third-party actions pinned to immutable commit SHAs.
7. Add artifact attestations for distributable release assets once the release workflow is ready to emit and verify them. Attestations establish provenance; they do not prove program correctness.
8. Add an SBOM to release evidence and bind it to the same source commit and artifact digest.
9. Progress toward a reviewed SLSA-compatible provenance path for release artifacts without weakening Habitat's existing reproducible-build evidence.

## Enforcement boundary

Repository rules protect repository transitions; Habitat's own Truth Plane protects evidence and source/revision semantics. Neither substitutes for the other. A green CI run does not prove universal correctness, and a GitHub ruleset does not make weak evidence strong.

Any future document that says branch protection, required checks, rulesets, artifact attestations, SBOM enforcement, or provenance enforcement are "enabled" must be backed by fresh repository configuration or release evidence rather than this desired-state section.

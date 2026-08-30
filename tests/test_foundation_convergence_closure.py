from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "FOUNDATION-CONVERGENCE-CLOSURE.json"
SPEC_PATH = "docs/design/FOUNDATION-CONVERGENCE.md"

CRITERIA = (
    "Existing alpha.19 public protocol and MCP compatibility tests pass.",
    "Existing workspaces migrate/open without destructive loss.",
    "Semantic precision is benchmarked across multiple languages/providers instead of described only by capability detection.",
    "Every high-impact semantic/evidence object has explicit provenance and authority class.",
    "Read-only protocol operations remain state-neutral.",
    "Mutation/recovery/fault-injection suites remain green.",
    "Major cognitive subsystems have controlled ablation evidence.",
    "At least one soft policy is improved by the Learning Plane on held-out tasks and promoted through an independent evaluation gate.",
    "Learned policy rollback restores the exact previous policy and reproduces its benchmark fingerprint within declared tolerance.",
    "Repository current-version/docs/release identity is machine-consistent.",
    "No learning mechanism can edit or override constitutional invariants.",
    "Observatory can be disabled without disabling the control/cognition/runtime core.",
)

REQUIRED_EVIDENCE = {
    1: {"tests/test_protocol_conformance.py", "habitat/mcp_adapter.py", ".github/workflows/ci.yml"},
    2: {"tests/test_storage_migrations.py"},
    3: {
        "benchmarks/semantic_precision_matrix.py",
        "tests/test_semantic_precision_matrix.py",
        "tests/test_semantic_precision_ci_gate.py",
        ".github/workflows/ci.yml",
    },
    4: {"tests/test_truth_adapters.py", "tests/test_truth_authority.py"},
    5: {"tests/test_protocol_conformance.py"},
    6: {
        "tests/test_db_recovery_suite.py",
        "tests/test_mutation_recovery_suite.py",
        "tests/test_reliability_suite.py",
        ".github/workflows/ci.yml",
    },
    7: {"tests/test_benchmark_wave4_closure.py", "tests/test_benchmark_strong_harness.py"},
    8: {"tests/test_learning_plane_heldout_promotion.py"},
    9: {"tests/test_learning_plane_heldout_promotion.py"},
    10: {"tools/check_release_identity.py", "tests/test_release_identity_consistency.py", ".github/workflows/ci.yml"},
    11: {"tests/test_learning_plane_heldout_promotion.py", "tests/test_learning_context_policy_runtime.py"},
    12: {"tests/test_observatory_headless.py", "tests/test_observatory_projection_faults.py"},
}


class FoundationConvergenceClosureManifestTests(unittest.TestCase):
    def load_manifest(self) -> dict:
        self.assertTrue(MANIFEST.is_file(), "closure evidence manifest must exist")
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_preserves_exact_spec_criteria_and_is_only_an_evidence_index(self):
        manifest = self.load_manifest()
        self.assertEqual(1, manifest["schema"])
        self.assertEqual("foundation-convergence-closure", manifest["suite"])
        self.assertEqual(SPEC_PATH, manifest["spec_path"])
        self.assertNotIn("passed", manifest)
        self.assertNotIn("complete", manifest)

        entries = manifest["criteria"]
        self.assertEqual(list(range(1, 13)), [entry["id"] for entry in entries])
        self.assertEqual(list(CRITERIA), [entry["criterion"] for entry in entries])
        for entry in entries:
            self.assertNotIn("passed", entry)
            self.assertNotIn("complete", entry)
            evidence = entry["evidence"]
            self.assertTrue(evidence)
            self.assertTrue(all(isinstance(path, str) and path.strip() for path in evidence))

    def test_manifest_references_existing_executable_evidence_for_every_criterion(self):
        manifest = self.load_manifest()
        by_id = {entry["id"]: entry for entry in manifest["criteria"]}
        for criterion_id, required in REQUIRED_EVIDENCE.items():
            with self.subTest(criterion_id=criterion_id):
                evidence = set(by_id[criterion_id]["evidence"])
                self.assertTrue(required <= evidence)
                for path in evidence:
                    target = ROOT / path
                    self.assertTrue(target.is_file(), f"missing evidence path: {path}")
                self.assertTrue(
                    any(
                        path.startswith(("tests/", "tools/", "benchmarks/", ".github/workflows/"))
                        for path in evidence
                    ),
                    "criterion must include executable or CI evidence, not prose alone",
                )

    def test_claim_boundary_is_narrow_and_rejects_universal_or_agi_interpretation(self):
        boundary = self.load_manifest()["claim_boundary"]
        lowered = boundary.lower()
        self.assertIn("repository-defined", lowered)
        self.assertIn("tested", lowered)
        self.assertIn("not", lowered)
        self.assertIn("agi", lowered)
        self.assertIn("universal", lowered)
        self.assertIn("superiority", lowered)


if __name__ == "__main__":
    unittest.main()

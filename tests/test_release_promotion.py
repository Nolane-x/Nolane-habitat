import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from habitat.release import ReleaseManifest, evaluate_promotion
from tools.promote_release import main


class ReleasePromotionTests(unittest.TestCase):
    def test_promotion_blocks_when_required_evidence_is_missing(self):
        manifest = ReleaseManifest(
            version="0.1.0-alpha.19",
            commit="commit",
            reports={"semantic": "digest"},
            artifact_hashes={},
            residual_risks=(),
        )

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("truth-core", verdict.missing_reports)
        self.assertIn("matrix", verdict.missing_reports)

    def test_promotion_rejects_empty_or_non_digest_evidence(self):
        manifest = ReleaseManifest(
            version="0.1.0-alpha.19",
            commit="commit",
            reports={
                "truth-core": "not-a-digest",
                "matrix": "also-not-a-digest",
                "faults": "missing",
                "artifacts": "placeholder",
            },
            artifact_hashes={},
            residual_risks=(),
        )

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("report:truth-core:invalid-digest", verdict.failed_gates)
        self.assertIn("artifact_hashes:missing", verdict.failed_gates)

    def test_alpha_candidate_requires_scanner_and_independent_reviewer_binding(self):
        manifest = ReleaseManifest(
            version="0.1.0-alpha.20",
            commit="a" * 40,
            reports={
                "truth-core": "1" * 64,
                "matrix": "2" * 64,
                "faults": "3" * 64,
                "artifacts": "4" * 64,
                "scanner": "5" * 64,
            },
            artifact_hashes={"wheel": "b" * 64},
            residual_risks=(),
        )

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("reviewer_hashes:missing", verdict.failed_gates)

    def test_alpha_candidate_rejects_reviewer_hash_that_equals_an_artifact_hash(self):
        digest = "b" * 64
        manifest = ReleaseManifest(
            version="0.1.0-alpha.20",
            commit="a" * 40,
            reports={
                "truth-core": "1" * 64,
                "matrix": "2" * 64,
                "faults": "3" * 64,
                "artifacts": "4" * 64,
                "scanner": "5" * 64,
            },
            artifact_hashes={"wheel": digest},
            residual_risks=(),
            reviewer_hashes=(digest,),
        )

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("reviewer_hashes:not-independent", verdict.failed_gates)

    def test_dry_run_writes_a_blocked_verdict_without_publication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.json"
            output = root / "reports" / "verdict.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": "0.1.0-alpha.19",
                        "commit": "commit",
                        "reports": {},
                        "artifact_hashes": {},
                        "residual_risks": ["scanner unavailable"],
                    }
                ),
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "--manifest",
                    str(manifest),
                    "--target",
                    "alpha-candidate",
                    "--dry-run",
                    "--out",
                    str(output),
                ]
            )

            verdict = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(1, exit_code)
            self.assertEqual("not-attempted", verdict["publication"])
            self.assertEqual(
                ["artifacts", "faults", "matrix", "scanner", "truth-core"],
                verdict["required_reports"],
            )
            self.assertFalse(verdict["verdict"]["admitted"])

    def test_release_gate_script_is_runnable_from_a_checkout(self):
        root = Path(__file__).parents[1]

        result = subprocess.run(
            [sys.executable, "tools/promote_release.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--manifest", result.stdout)


if __name__ == "__main__":
    unittest.main()

import json
import hashlib
import io
from dataclasses import replace
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from habitat.release import REQUIRED_REPORTS, ReleaseManifest, evaluate_promotion
from tools.promote_release import main


class ReleasePromotionTests(unittest.TestCase):
    @staticmethod
    def _provenance(
        commit: str, *, status: str = "passed", evidence_type: str = "report"
    ) -> dict[str, str]:
        payload = {
            "schema": 1,
            "suite": "release-evidence",
            "evidence_type": evidence_type,
            "source_commit": commit,
            "status": status,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "source_commit": commit,
            "status": status,
            "report_sha256": digest,
            "evidence_type": evidence_type,
            "schema": 1,
        }

    @staticmethod
    def _with_manifest_hash(manifest: ReleaseManifest) -> ReleaseManifest:
        unsigned = manifest.as_dict()
        unsigned.pop("manifest_sha256")
        digest = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return replace(manifest, manifest_sha256=digest)

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

    def test_alpha_candidate_requires_scanner_and_review_binding(self):
        manifest = self._with_manifest_hash(ReleaseManifest(
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
        ))

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("reviewer_hashes:missing", verdict.failed_gates)

    def test_alpha_candidate_requires_source_mutation_recovery_evidence(self):
        commit = "a" * 40
        required_without_mutation_recovery = {
            "truth-core", "matrix", "faults", "artifacts", "scanner", "db-recovery", "contract"
        }
        manifest = self._with_manifest_hash(ReleaseManifest(
            version="0.1.0-alpha.20",
            commit=commit,
            reports={
                name: f"{index:x}" * 64
                for index, name in enumerate(sorted(required_without_mutation_recovery), start=1)
            },
            artifact_hashes={"wheel": "b" * 64},
            residual_risks=(),
            reviewer_hashes=("c" * 64,),
            report_provenance={name: self._provenance(commit) for name in required_without_mutation_recovery},
        ))

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("mutation-recovery", verdict.missing_reports)

    def test_alpha_candidate_requires_reproducible_build_evidence(self):
        commit = "a" * 40
        required_without_reproducible_build = {
            "truth-core", "matrix", "faults", "artifacts", "scanner", "db-recovery", "mutation-recovery", "protocol-conformance", "contract"
        }
        manifest = self._with_manifest_hash(ReleaseManifest(
            version="0.1.0-alpha.20",
            commit=commit,
            reports={
                name: f"{index:x}" * 64
                for index, name in enumerate(sorted(required_without_reproducible_build), start=1)
            },
            artifact_hashes={"wheel": "b" * 64},
            residual_risks=(),
            reviewer_hashes=("c" * 64,),
            report_provenance={name: self._provenance(commit) for name in required_without_reproducible_build},
        ))

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("reproducible-build", verdict.missing_reports)

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
        self.assertIn("reviewer_hashes:reused-evidence", verdict.failed_gates)

    def test_alpha_candidate_rejects_reports_without_matching_passed_provenance(self):
        commit = "a" * 40
        required = {
            "truth-core", "matrix", "faults", "artifacts", "scanner", "db-recovery", "mutation-recovery", "reproducible-build", "protocol-conformance", "contract"
        }
        manifest = ReleaseManifest(
            version="0.1.0-alpha.20",
            commit=commit,
            reports={name: str(index) * 64 for index, name in enumerate(sorted(required), start=1)},
            artifact_hashes={"wheel": "b" * 64},
            residual_risks=(),
            reviewer_hashes=("c" * 64,),
            report_provenance={
                name: self._provenance(commit) for name in required if name != "contract"
            } | {"contract": self._provenance("d" * 40, status="failed")},
        )

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("report:contract:source-commit-mismatch", verdict.failed_gates)
        self.assertIn("report:contract:status", verdict.failed_gates)

    def test_alpha_candidate_accepts_complete_passed_commit_bound_evidence(self):
        commit = "a" * 40
        required = {
            "truth-core", "matrix", "faults", "artifacts", "scanner", "db-recovery", "mutation-recovery", "reproducible-build", "protocol-conformance", "contract"
        }
        manifest = self._with_manifest_hash(ReleaseManifest(
            version="0.1.0-alpha.20",
            commit=commit,
            reports={name: f"{index:x}" * 64 for index, name in enumerate(sorted(required), start=1)},
            artifact_hashes={"wheel": "b" * 64},
            residual_risks=(),
            reviewer_hashes=("c" * 64,),
            reviewers={"review": "c" * 64},
            report_provenance={name: self._provenance(commit) for name in required},
            review_provenance={"review": self._provenance(commit, evidence_type="review")},
        ))

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertTrue(verdict.admitted, verdict.failed_gates)

    def test_alpha_candidate_rejects_review_with_a_reused_canonical_report_payload(self):
        commit = "a" * 40
        required = REQUIRED_REPORTS["alpha-candidate"]
        report_provenance = {name: self._provenance(commit) for name in required}
        reused_digest = report_provenance["contract"]["report_sha256"]
        review_provenance = self._provenance(commit, evidence_type="review")
        review_provenance["report_sha256"] = reused_digest
        manifest = self._with_manifest_hash(ReleaseManifest(
            version="0.1.0-alpha.20", commit=commit,
            reports={name: f"{index:x}" * 64 for index, name in enumerate(sorted(required), start=1)},
            artifact_hashes={"wheel": "b" * 64}, residual_risks=(),
            reviewer_hashes=("c" * 64,), reviewers={"review": "c" * 64},
            report_provenance=report_provenance,
            review_provenance={"review": review_provenance},
        ))

        verdict = evaluate_promotion(manifest, target="alpha-candidate")

        self.assertFalse(verdict.admitted)
        self.assertIn("review:review:reused-report-payload", verdict.failed_gates)

    def test_dry_run_writes_a_blocked_verdict_without_publication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.json"
            output = root / "reports" / "verdict.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": "0.1.0-alpha.19",
                        "commit": "a" * 40,
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
                ["artifacts", "contract", "db-recovery", "faults", "matrix", "mutation-recovery", "protocol-conformance", "reproducible-build", "scanner", "truth-core"],
                verdict["required_reports"],
            )
            self.assertFalse(verdict["verdict"]["admitted"])

    def test_dry_run_refuses_invalid_commit_without_writing_a_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.json"
            output = root / "verdict.json"
            manifest.write_text(
                json.dumps({
                    "version": "0.1.0-alpha.20", "commit": "invalid",
                    "reports": {}, "artifact_hashes": {}, "residual_risks": [],
                }),
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                main(["--manifest", str(manifest), "--target", "alpha-candidate", "--dry-run", "--out", str(output)])
            self.assertEqual(2, raised.exception.code)
            self.assertIn("manifest:commit:invalid-sha", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_dry_run_binds_a_hashed_verdict_to_the_evaluated_manifest(self):
        commit = "a" * 40
        required = REQUIRED_REPORTS["alpha-candidate"]
        valid = self._with_manifest_hash(ReleaseManifest(
            version="0.1.0-alpha.20", commit=commit,
            reports={name: f"{index:x}" * 64 for index, name in enumerate(sorted(required), start=1)},
            artifact_hashes={"wheel": "b" * 64}, residual_risks=(),
            reviewer_hashes=("c" * 64,), reviewers={"review": "c" * 64},
            report_provenance={name: self._provenance(commit) for name in required},
            review_provenance={"review": self._provenance(commit, evidence_type="review")},
        ))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.json"
            output = root / "verdict.json"
            manifest.write_text(json.dumps(valid.as_dict()), encoding="utf-8")

            self.assertEqual(0, main(["--manifest", str(manifest), "--target", "alpha-candidate", "--dry-run", "--out", str(output)]))

            value = json.loads(output.read_text(encoding="utf-8"))
            unsigned = dict(value)
            reported_digest = unsigned.pop("report_sha256")
            self.assertEqual(commit, value["source_commit"])
            self.assertEqual(valid.manifest_sha256, value["manifest_sha256"])
            self.assertEqual(
                hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
                reported_digest,
            )

    def test_dry_run_rejects_duplicate_manifest_keys_without_writing_a_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.json"
            output = root / "verdict.json"
            manifest.write_text('{"version":"one","version":"two"}', encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                main(["--manifest", str(manifest), "--target", "alpha-candidate", "--dry-run", "--out", str(output)])
            self.assertEqual(2, raised.exception.code)
            self.assertIn("duplicate JSON key: version", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_dry_run_rejects_missing_or_tampered_manifest_self_hash(self):
        commit = "a" * 40
        required = REQUIRED_REPORTS["alpha-candidate"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, digest in (("missing", None), ("tampered", "0" * 64)):
                with self.subTest(name=name):
                    manifest = root / f"{name}-manifest.json"
                    output = root / f"{name}-verdict.json"
                    value = {
                        "version": "0.1.0-alpha.20",
                        "commit": commit,
                        "reports": {
                            report_name: f"{index:x}" * 64
                            for index, report_name in enumerate(sorted(required), start=1)
                        },
                        "artifact_hashes": {"wheel": "b" * 64},
                        "residual_risks": [],
                        "reviewer_hashes": ["c" * 64],
                        "report_provenance": {
                            report_name: self._provenance(commit)
                            for report_name in required
                        },
                    }
                    if digest:
                        value["manifest_sha256"] = digest
                    manifest.write_text(json.dumps(value), encoding="utf-8")

                    exit_code = main(
                        [
                            "--manifest", str(manifest), "--target", "alpha-candidate",
                            "--dry-run", "--out", str(output),
                        ]
                    )

                    verdict = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(1, exit_code)
                    self.assertIn(
                        "manifest:self-hash:invalid",
                        verdict["verdict"]["failed_gates"],
                    )

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

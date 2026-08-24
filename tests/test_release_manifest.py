import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from habitat.release import REQUIRED_REPORTS, build_release_manifest
from tools.build_release_manifest import main


class ReleaseManifestTests(unittest.TestCase):
    @staticmethod
    def _commit_bound_report(
        commit: str, *, status: str = "passed", evidence_type: str = "report"
    ) -> dict:
        report = {
            "schema": 1,
            "suite": "release-evidence",
            "evidence_type": evidence_type,
            "source_commit": commit,
            "status": status,
        }
        report["report_sha256"] = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return report

    def _required_report_paths(self, root: Path, commit: str) -> dict[str, Path]:
        reports: dict[str, Path] = {}
        for name in REQUIRED_REPORTS["alpha-candidate"]:
            path = root / f"{name}.json"
            path.write_text(
                json.dumps(self._commit_bound_report(commit)), encoding="utf-8"
            )
            reports[name] = path
        return reports

    def test_manifest_binds_evidence_and_artifacts_to_file_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "matrix.json"
            artifact = root / "habitat.whl"
            report.write_bytes(b'{"passed": true}\n')
            artifact.write_bytes(b"wheel bytes")

            manifest = build_release_manifest(
                version="0.1.0-alpha.19",
                commit="commit",
                reports={"matrix": report},
                artifacts={"wheel": artifact},
                residual_risks=("scanner unavailable",),
            )

            self.assertEqual(
                hashlib.sha256(report.read_bytes()).hexdigest(),
                manifest.reports["matrix"],
            )
            self.assertEqual(
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
                manifest.artifact_hashes["wheel"],
            )
            self.assertEqual(("scanner unavailable",), manifest.residual_risks)

    def test_manifest_cli_writes_hash_bound_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            commit = "a" * 40
            reports = self._required_report_paths(root, commit)
            artifact = root / "habitat.whl"
            review = root / "review.json"
            output = root / "release-manifest.json"
            artifact.write_text("wheel", encoding="utf-8")
            review.write_text(
                json.dumps(self._commit_bound_report(commit, evidence_type="review")),
                encoding="utf-8",
            )

            args = [
                "--version", "0.1.0-alpha.20", "--commit", commit,
                "--target", "alpha-candidate", "--artifact", f"wheel={artifact}",
                "--review", f"review={review}", "--out", str(output),
            ]
            for name, path in reports.items():
                args.extend(("--report", f"{name}={path}"))
            exit_code = main(args)

            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0, exit_code)
            self.assertEqual("0.1.0-alpha.20", value["version"])
            self.assertEqual(
                hashlib.sha256(reports["matrix"].read_bytes()).hexdigest(),
                value["reports"]["matrix"],
            )

    def test_manifest_cli_binds_a_named_commit_bound_review_record(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            commit = "a" * 40
            reports = self._required_report_paths(root, commit)
            artifact = root / "habitat.whl"
            review = root / "review.json"
            output = root / "release-manifest.json"
            artifact.write_bytes(b"wheel bytes")
            review.write_text(
                json.dumps(self._commit_bound_report(commit, evidence_type="review")),
                encoding="utf-8",
            )

            args = [
                "--version", "0.1.0-alpha.20", "--commit", commit,
                "--target", "alpha-candidate", "--artifact", f"wheel={artifact}",
                "--review", f"review={review}", "--out", str(output),
            ]
            for name, path in reports.items():
                args.extend(("--report", f"{name}={path}"))
            exit_code = main(args)

            value = json.loads(output.read_text(encoding="utf-8"))
            digest = hashlib.sha256(review.read_bytes()).hexdigest()
            self.assertEqual(0, exit_code)
            self.assertEqual([digest], value["reviewer_hashes"])
            self.assertEqual({"review": digest}, value["reviewers"])
            self.assertEqual(commit, value["review_provenance"]["review"]["source_commit"])

    def test_manifest_records_verified_report_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "matrix.json"
            commit = "a" * 40
            report.write_text(
                json.dumps(self._commit_bound_report(commit)), encoding="utf-8"
            )

            manifest = build_release_manifest(
                version="0.1.0-alpha.20",
                commit=commit,
                reports={"matrix": report},
                artifacts={},
            )

            self.assertEqual(
                {
                    "source_commit": commit,
                    "status": "passed",
                    "report_sha256": self._commit_bound_report(commit)["report_sha256"],
                },
                manifest.report_provenance["matrix"],
            )

    def test_manifest_serializes_a_stable_self_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "matrix.json"
            artifact = root / "habitat.whl"
            report.write_text(
                json.dumps(self._commit_bound_report("a" * 40)), encoding="utf-8"
            )
            artifact.write_bytes(b"wheel bytes")

            first = build_release_manifest(
                version="0.1.0-alpha.20",
                commit="a" * 40,
                reports={"matrix": report},
                artifacts={"wheel": artifact},
            )
            second = build_release_manifest(
                version="0.1.0-alpha.20",
                commit="a" * 40,
                reports={"matrix": report},
                artifacts={"wheel": artifact},
            )

            self.assertRegex(first.manifest_sha256, r"^[0-9a-f]{64}$")
            self.assertEqual(first.manifest_sha256, second.manifest_sha256)
            self.assertEqual(first.manifest_sha256, first.as_dict()["manifest_sha256"])

    def test_cli_rejects_missing_failed_or_cross_commit_admission_evidence(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "habitat.whl"
            review = root / "review.json"
            output = root / "release-manifest.json"
            artifact.write_bytes(b"wheel bytes")
            review.write_text(
                json.dumps(self._commit_bound_report(commit, evidence_type="review")),
                encoding="utf-8",
            )

            cases = (
                ("missing", {}, None),
                ("failed", self._required_report_paths(root, commit), "failed"),
                ("cross-commit", self._required_report_paths(root, commit), "b" * 40),
            )
            for name, reports, corruption in cases:
                with self.subTest(name=name):
                    if corruption == "failed":
                        reports["contract"].write_text(
                            json.dumps(self._commit_bound_report(commit, status="failed")),
                            encoding="utf-8",
                        )
                    elif corruption:
                        reports["contract"].write_text(
                            json.dumps(self._commit_bound_report(corruption)),
                            encoding="utf-8",
                        )
                    args = [
                        "--version", "0.1.0-alpha.20", "--commit", commit,
                        "--target", "alpha-candidate", "--artifact", f"wheel={artifact}",
                        "--review", f"review={review}", "--out", str(output),
                    ]
                    for report_name, report_path in reports.items():
                        args.extend(("--report", f"{report_name}={report_path}"))
                    with self.assertRaises(SystemExit):
                        main(args)

    def test_manifest_script_runs_from_a_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            commit = "a" * 40
            reports = {}
            for name in REQUIRED_REPORTS["beta-readiness"]:
                path = root / f"{name}.json"
                path.write_text(
                    json.dumps(self._commit_bound_report(commit)), encoding="utf-8"
                )
                reports[name] = path
            output = root / "release-manifest.json"
            repository = Path(__file__).parents[1]

            args = [
                sys.executable, "tools/build_release_manifest.py",
                "--version", "0.1.0-alpha.20", "--commit", commit,
                "--target", "beta-readiness", "--out", str(output),
            ]
            for name, path in reports.items():
                args.extend(("--report", f"{name}={path}"))
            result = subprocess.run(
                args,
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()

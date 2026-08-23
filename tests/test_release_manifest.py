import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from habitat.release import build_release_manifest
from tools.build_release_manifest import main


class ReleaseManifestTests(unittest.TestCase):
    @staticmethod
    def _commit_bound_report(commit: str, *, status: str = "passed") -> dict:
        report = {
            "schema": 1,
            "suite": "release-evidence",
            "source_commit": commit,
            "status": status,
        }
        report["report_sha256"] = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return report

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
            report = root / "matrix.json"
            artifact = root / "habitat.whl"
            output = root / "release-manifest.json"
            report.write_text("matrix", encoding="utf-8")
            artifact.write_text("wheel", encoding="utf-8")

            exit_code = main(
                [
                    "--version",
                    "0.1.0-alpha.19",
                    "--commit",
                    "commit",
                    "--report",
                    f"matrix={report}",
                    "--artifact",
                    f"wheel={artifact}",
                    "--risk",
                    "scanner unavailable",
                    "--out",
                    str(output),
                ]
            )

            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0, exit_code)
            self.assertEqual("0.1.0-alpha.19", value["version"])
            self.assertEqual(hashlib.sha256(b"matrix").hexdigest(), value["reports"]["matrix"])

    def test_manifest_cli_binds_a_named_independent_review_record(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            review = root / "independent-review.json"
            output = root / "release-manifest.json"
            review.write_text('{"reviewer":"independent"}', encoding="utf-8")

            exit_code = main(
                [
                    "--version",
                    "0.1.0-alpha.20",
                    "--commit",
                    "a" * 40,
                    "--review",
                    f"independent-review={review}",
                    "--out",
                    str(output),
                ]
            )

            value = json.loads(output.read_text(encoding="utf-8"))
            digest = hashlib.sha256(review.read_bytes()).hexdigest()
            self.assertEqual(0, exit_code)
            self.assertEqual([digest], value["reviewer_hashes"])
            self.assertEqual({"independent-review": digest}, value["reviewers"])

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

    def test_manifest_script_runs_from_a_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "matrix.json"
            output = root / "release-manifest.json"
            report.write_text("matrix", encoding="utf-8")
            repository = Path(__file__).parents[1]

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/build_release_manifest.py",
                    "--version",
                    "0.1.0-alpha.19",
                    "--commit",
                    "commit",
                    "--report",
                    f"matrix={report}",
                    "--out",
                    str(output),
                ],
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()

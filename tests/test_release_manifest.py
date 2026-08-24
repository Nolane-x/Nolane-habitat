import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from habitat.release import REQUIRED_REPORTS, ReleaseManifest, build_release_manifest
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

    def _alpha_args(
        self, reports: dict[str, Path], artifact: Path, review: Path, output: Path, commit: str
    ) -> list[str]:
        args = [
            "--version", "0.1.0-alpha.20", "--commit", commit,
            "--target", "alpha-candidate", "--artifact", f"wheel={artifact}",
            "--review", f"review={review}", "--out", str(output),
        ]
        for name, path in reports.items():
            args.extend(("--report", f"{name}={path}"))
        return args

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
                    "evidence_type": "report",
                    "schema": 1,
                },
                manifest.report_provenance["matrix"],
            )

    def test_manifest_uses_one_path_open_snapshot_for_each_report_and_review(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "matrix.json"
            review = root / "review.json"
            report.write_bytes(b"placeholder")
            review.write_bytes(b"placeholder")
            first_report = json.dumps(self._commit_bound_report(commit)).encode("utf-8")
            first_review = json.dumps(
                self._commit_bound_report(commit, evidence_type="review")
            ).encode("utf-8")
            second_report = json.dumps(self._commit_bound_report("b" * 40)).encode("utf-8")
            second_review = json.dumps(
                self._commit_bound_report("b" * 40, evidence_type="review")
            ).encode("utf-8")
            snapshots = {
                report: [first_report, second_report],
                review: [first_review, second_review],
            }
            reads: list[tuple[Path, str]] = []

            def changing_open(path: Path, mode: str = "r", *args, **kwargs):
                reads.append((path, mode))
                snapshot = snapshots[path].pop(0)
                if "b" in mode:
                    return io.BytesIO(snapshot)
                return io.StringIO(snapshot.decode("utf-8"))

            with patch.object(Path, "open", new=changing_open):
                manifest = build_release_manifest(
                    version="0.1.0-alpha.20", commit=commit,
                    reports={"matrix": report}, artifacts={}, reviewers={"review": review},
                )

            self.assertEqual([(report, "rb"), (review, "rb")], reads)
            self.assertEqual(hashlib.sha256(first_report).hexdigest(), manifest.reports["matrix"])
            self.assertEqual(
                self._commit_bound_report(commit)["report_sha256"],
                manifest.report_provenance["matrix"]["report_sha256"],
            )
            self.assertEqual(
                self._commit_bound_report(commit, evidence_type="review")["report_sha256"],
                manifest.review_provenance["review"]["report_sha256"],
            )

    def test_manifest_hashes_distribution_artifacts_in_bounded_blocks(self):
        payload = b"artifact-block-" * 100_000
        read_sizes = []

        class BoundedReader(io.BytesIO):
            def read(self, size=-1):
                if size < 0:
                    raise AssertionError("artifact was buffered with an unbounded read")
                read_sizes.append(size)
                return super().read(size)

        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "habitat.whl"
            artifact.write_bytes(payload)

            with patch.object(
                Path,
                "open",
                new=lambda path, mode="r", *args, **kwargs: BoundedReader(payload),
            ):
                manifest = build_release_manifest(
                    version="0.1.0-alpha.20",
                    commit="a" * 40,
                    reports={},
                    artifacts={"wheel": artifact},
                )

        self.assertEqual(hashlib.sha256(payload).hexdigest(), manifest.artifact_hashes["wheel"])
        self.assertGreater(len(read_sizes), 1)
        self.assertTrue(all(0 < size <= 1024 * 1024 for size in read_sizes))

    def test_manifest_round_trips_through_its_in_memory_dictionary(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "matrix.json"
            report.write_text(json.dumps(self._commit_bound_report(commit)), encoding="utf-8")
            manifest = build_release_manifest(
                version="0.1.0-alpha.20", commit=commit,
                reports={"matrix": report}, artifacts={}, residual_risks=("known risk",),
            )

            self.assertEqual(manifest, ReleaseManifest.from_dict(manifest.as_dict()))

    def test_manifest_rejects_appended_semantic_fields(self):
        value = {
            "version": "0.1.0-alpha.20",
            "commit": "a" * 40,
            "release_channel": "stable",
        }

        with self.assertRaisesRegex(
            ValueError, "manifest has unknown fields: release_channel"
        ):
            ReleaseManifest.from_dict(value)

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

    def test_cli_rejects_each_invalid_admission_evidence_with_a_gate_and_no_output(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "habitat.whl"
            review = root / "review.json"
            artifact.write_bytes(b"wheel bytes")
            review.write_text(
                json.dumps(self._commit_bound_report(commit, evidence_type="review")),
                encoding="utf-8",
            )

            cases = (
                ("missing", {}, None, "reports:required-set-mismatch"),
                ("failed", self._required_report_paths(root, commit), "failed", "report:contract:status"),
                ("cross-commit", self._required_report_paths(root, commit), "b" * 40, "report:contract:source-commit-mismatch"),
                ("tampered", self._required_report_paths(root, commit), "tampered", "report:contract:provenance:missing-or-invalid"),
            )
            for name, reports, corruption, expected_gate in cases:
                with self.subTest(name=name):
                    output = root / f"{name}-release-manifest.json"
                    if corruption == "failed":
                        reports["contract"].write_text(
                            json.dumps(self._commit_bound_report(commit, status="failed")),
                            encoding="utf-8",
                        )
                    elif corruption == "tampered":
                        value = self._commit_bound_report(commit)
                        value["status"] = "failed"
                        reports["contract"].write_text(json.dumps(value), encoding="utf-8")
                    elif corruption:
                        reports["contract"].write_text(
                            json.dumps(self._commit_bound_report(corruption)),
                            encoding="utf-8",
                        )
                    stderr = io.StringIO()
                    with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                        main(self._alpha_args(reports, artifact, review, output, commit))
                    self.assertEqual(2, raised.exception.code)
                    self.assertIn(expected_gate, stderr.getvalue())
                    self.assertFalse(output.exists())

    def test_cli_rejects_duplicate_evidence_names_and_duplicate_json_keys(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reports = self._required_report_paths(root, commit)
            artifact = root / "habitat.whl"
            review = root / "review.json"
            artifact.write_bytes(b"wheel bytes")
            review.write_text(
                json.dumps(self._commit_bound_report(commit, evidence_type="review")),
                encoding="utf-8",
            )
            duplicate_name_output = root / "duplicate-name.json"
            duplicate_json_output = root / "duplicate-json.json"

            stderr = io.StringIO()
            duplicate_name_args = self._alpha_args(
                reports, artifact, review, duplicate_name_output, commit
            ) + ["--report", f"contract={reports['contract']}"]
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                main(duplicate_name_args)
            self.assertEqual(2, raised.exception.code)
            self.assertIn("duplicate evidence name: contract", stderr.getvalue())
            self.assertFalse(duplicate_name_output.exists())

            payload = self._commit_bound_report(commit)
            duplicate_json = json.dumps(payload).replace(
                '"status": "passed"', '"status": "failed", "status": "passed"'
            )
            reports["contract"].write_text(duplicate_json, encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                main(self._alpha_args(reports, artifact, review, duplicate_json_output, commit))
            self.assertEqual(2, raised.exception.code)
            self.assertIn("duplicate JSON key: status", stderr.getvalue())
            self.assertFalse(duplicate_json_output.exists())

    def test_cli_rejects_a_reserialized_report_used_as_a_review(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reports = self._required_report_paths(root, commit)
            artifact = root / "habitat.whl"
            review = root / "review.json"
            output = root / "release-manifest.json"
            artifact.write_bytes(b"wheel bytes")
            review.write_text(
                json.dumps(self._commit_bound_report(commit), indent=2), encoding="utf-8"
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                main(self._alpha_args(reports, artifact, review, output, commit))
            self.assertEqual(2, raised.exception.code)
            self.assertIn("review:review:invalid-kind", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_rejects_a_review_bound_to_a_different_commit(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reports = self._required_report_paths(root, commit)
            artifact = root / "habitat.whl"
            review = root / "review.json"
            output = root / "release-manifest.json"
            artifact.write_bytes(b"wheel bytes")
            review.write_text(
                json.dumps(self._commit_bound_report("b" * 40, evidence_type="review")),
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                main(self._alpha_args(reports, artifact, review, output, commit))
            self.assertEqual(2, raised.exception.code)
            self.assertIn("review:review:source-commit-mismatch", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_manifest_hash_is_stable_when_named_reviews_are_reordered(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "report.json"
            first = root / "first.json"
            second = root / "second.json"
            report.write_text(json.dumps(self._commit_bound_report(commit)), encoding="utf-8")
            first.write_text(
                json.dumps(self._commit_bound_report(commit, evidence_type="review")),
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(self._commit_bound_report(commit, evidence_type="review")) + "\n",
                encoding="utf-8",
            )
            one = build_release_manifest(
                version="0.1.0-alpha.20", commit=commit, reports={"matrix": report},
                artifacts={}, reviewers={"first": first, "second": second},
            )
            two = build_release_manifest(
                version="0.1.0-alpha.20", commit=commit, reports={"matrix": report},
                artifacts={}, reviewers={"second": second, "first": first},
            )
            self.assertEqual(one.manifest_sha256, two.manifest_sha256)

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

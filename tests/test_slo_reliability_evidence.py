from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from habitat.operations.slo import SloProfile, SloSample
from tools import run_reliability_suite


class SloReliabilityEvidenceTests(unittest.TestCase):
    def _profile(self) -> SloProfile:
        return SloProfile(
            profile_id="local-1k",
            required_success_ratio=1.0,
            max_median_regression=0.20,
            max_peak_memory_regression=0.20,
            required_cycles=2,
        )

    def _samples(self) -> tuple[SloSample, ...]:
        return (
            SloSample(
                scenario_id="cycle-b",
                completed=True,
                latency_ms=110.0,
                peak_memory_bytes=1100,
                baseline_latency_ms=100.0,
                baseline_peak_memory_bytes=1000,
            ),
            SloSample(
                scenario_id="cycle-a",
                completed=True,
                latency_ms=105.0,
                peak_memory_bytes=1050,
                baseline_latency_ms=100.0,
                baseline_peak_memory_bytes=1000,
            ),
        )

    def test_normalized_slo_evidence_is_commit_bound_reproducible_and_sorted(self):
        normalizer = getattr(run_reliability_suite, "normalize_slo_evidence", None)
        self.assertIsNotNone(
            normalizer,
            "reliability runner must expose normalize_slo_evidence",
        )
        commit = "a" * 40
        report = normalizer(
            source_commit=commit,
            profile=self._profile(),
            samples=self._samples(),
        )

        self.assertEqual(1, report["schema"])
        self.assertEqual("operational-slo", report["suite"])
        self.assertEqual("report", report["evidence_type"])
        self.assertEqual(commit, report["source_commit"])
        self.assertEqual("passed", report["status"])
        self.assertTrue(report["evaluation"]["admitted"])
        self.assertEqual(
            ["cycle-a", "cycle-b"],
            [item["scenario_id"] for item in report["samples"]],
        )
        unsigned = dict(report)
        digest = unsigned.pop("report_sha256")
        expected = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(expected, digest)

    def test_missing_measurement_is_serialized_as_null_and_blocks_report(self):
        normalizer = getattr(run_reliability_suite, "normalize_slo_evidence", None)
        self.assertIsNotNone(normalizer)
        samples = (
            SloSample(
                scenario_id="cycle-a",
                completed=True,
                latency_ms=None,
                peak_memory_bytes=1000,
                baseline_latency_ms=100.0,
                baseline_peak_memory_bytes=1000,
            ),
            self._samples()[1],
        )
        report = normalizer(
            source_commit="b" * 40,
            profile=self._profile(),
            samples=samples,
        )

        self.assertEqual("failed", report["status"])
        self.assertIsNone(report["samples"][0]["latency_ms"])
        self.assertIsNone(report["evaluation"]["median_latency_regression"])
        self.assertIn(
            "missing-measurement:cycle-a:latency_ms",
            report["evaluation"]["reasons"],
        )

    def test_invalid_source_commit_is_rejected(self):
        normalizer = getattr(run_reliability_suite, "normalize_slo_evidence", None)
        self.assertIsNotNone(normalizer)
        with self.assertRaisesRegex(ValueError, "source commit"):
            normalizer(
                source_commit="not-a-commit",
                profile=self._profile(),
                samples=self._samples(),
            )

    def test_cli_accepts_external_measurements_and_writes_separate_slo_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profile_path = root / "profile.json"
            samples_path = root / "samples.json"
            faults_out = root / "faults.json"
            slo_out = root / "slo.json"
            profile_path.write_text(
                json.dumps({
                    "profile_id": "local-1k",
                    "required_success_ratio": 1.0,
                    "max_median_regression": 0.20,
                    "max_peak_memory_regression": 0.20,
                    "required_cycles": 2,
                }),
                encoding="utf-8",
            )
            samples_path.write_text(
                json.dumps([
                    {
                        "scenario_id": "cycle-b",
                        "completed": True,
                        "latency_ms": 110.0,
                        "peak_memory_bytes": 1100,
                        "baseline_latency_ms": 100.0,
                        "baseline_peak_memory_bytes": 1000,
                        "error": None,
                    },
                    {
                        "scenario_id": "cycle-a",
                        "completed": True,
                        "latency_ms": 105.0,
                        "peak_memory_bytes": 1050,
                        "baseline_latency_ms": 100.0,
                        "baseline_peak_memory_bytes": 1000,
                        "error": None,
                    },
                ]),
                encoding="utf-8",
            )

            exit_code = run_reliability_suite.main([
                "--source-commit", "c" * 40,
                "--out", str(faults_out),
                "--slo-profile", str(profile_path),
                "--slo-samples", str(samples_path),
                "--slo-out", str(slo_out),
            ])

            self.assertEqual(0, exit_code)
            self.assertTrue(faults_out.is_file())
            value = json.loads(slo_out.read_text(encoding="utf-8"))
            self.assertEqual("operational-slo", value["suite"])
            self.assertEqual("c" * 40, value["source_commit"])
            self.assertEqual("passed", value["status"])


if __name__ == "__main__":
    unittest.main()

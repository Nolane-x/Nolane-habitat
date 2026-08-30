from __future__ import annotations

import importlib
import json
import re
import unittest
from pathlib import Path


class SloAdmissionTests(unittest.TestCase):
    def _api(self):
        module_path = Path("habitat/operations/slo.py")
        self.assertTrue(
            module_path.is_file(),
            "Operational SLO admission kernel must exist at habitat/operations/slo.py",
        )
        return importlib.import_module("habitat.operations.slo")

    def _profile(self, api, *, required_cycles: int = 2):
        return api.SloProfile(
            profile_id="local-1k",
            required_success_ratio=1.0,
            max_median_regression=0.20,
            max_peak_memory_regression=0.20,
            required_cycles=required_cycles,
        )

    def _sample(
        self,
        api,
        scenario_id: str,
        *,
        completed: bool = True,
        latency_ms: float | None = 100.0,
        peak_memory_bytes: int | None = 1_000,
        baseline_latency_ms: float | None = 100.0,
        baseline_peak_memory_bytes: int | None = 1_000,
        error: str | None = None,
    ):
        return api.SloSample(
            scenario_id=scenario_id,
            completed=completed,
            latency_ms=latency_ms,
            peak_memory_bytes=peak_memory_bytes,
            baseline_latency_ms=baseline_latency_ms,
            baseline_peak_memory_bytes=baseline_peak_memory_bytes,
            error=error,
        )

    def test_no_samples_fail_closed_without_inventing_measurements(self):
        api = self._api()
        report = api.evaluate_slos(self._profile(api), ())

        self.assertFalse(report.admitted)
        self.assertEqual(0, report.total)
        self.assertEqual(0, report.completed)
        self.assertIsNone(report.median_latency_regression)
        self.assertIsNone(report.peak_memory_regression)
        self.assertIn("no-samples", report.reasons)

    def test_insufficient_cycles_fail_closed_even_when_observed_sample_passes(self):
        api = self._api()
        samples = (self._sample(api, "open-close-001"),)
        report = api.evaluate_slos(self._profile(api, required_cycles=2), samples)

        self.assertFalse(report.admitted)
        self.assertIn("insufficient-cycles", report.reasons)

    def test_missing_measurement_remains_missing_and_blocks_admission(self):
        api = self._api()
        samples = (
            self._sample(api, "open-close-001", latency_ms=None),
            self._sample(api, "open-close-002"),
        )
        report = api.evaluate_slos(self._profile(api), samples)

        self.assertFalse(report.admitted)
        self.assertIsNone(report.median_latency_regression)
        self.assertIn(
            "missing-measurement:open-close-001:latency_ms",
            report.reasons,
        )

    def test_success_ratio_failure_is_reported_separately_from_resource_metrics(self):
        api = self._api()
        samples = (
            self._sample(api, "open-close-001"),
            self._sample(
                api,
                "open-close-002",
                completed=False,
                error="fixture failure",
            ),
        )
        report = api.evaluate_slos(self._profile(api), samples)

        self.assertFalse(report.admitted)
        self.assertEqual(1, report.completed)
        self.assertIn("success-ratio", report.reasons)
        self.assertIn("open-close-002: fixture failure", report.failures)

    def test_latency_or_memory_regression_over_profile_limit_blocks_admission(self):
        api = self._api()
        samples = (
            self._sample(api, "open-close-001", latency_ms=121.0),
            self._sample(api, "open-close-002", latency_ms=121.0),
        )
        report = api.evaluate_slos(self._profile(api), samples)

        self.assertFalse(report.admitted)
        self.assertGreater(report.median_latency_regression, 0.20)
        self.assertIn("median-latency-regression", report.reasons)

    def test_passing_report_has_deterministic_serialization_and_fingerprint(self):
        api = self._api()
        samples = (
            self._sample(
                api,
                "open-close-001",
                latency_ms=110.0,
                peak_memory_bytes=1_100,
            ),
            self._sample(
                api,
                "open-close-002",
                latency_ms=110.0,
                peak_memory_bytes=1_100,
            ),
        )
        report = api.evaluate_slos(self._profile(api), samples)

        self.assertTrue(report.admitted, report.reasons)
        self.assertAlmostEqual(0.10, report.median_latency_regression)
        self.assertAlmostEqual(0.10, report.peak_memory_regression)
        first = report.canonical_json()
        second = report.canonical_json()
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(report.as_dict(), sort_keys=True, separators=(",", ":")),
            first,
        )
        self.assertRegex(report.fingerprint, re.compile(r"^[0-9a-f]{64}$"))


if __name__ == "__main__":
    unittest.main()

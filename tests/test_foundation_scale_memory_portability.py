from __future__ import annotations

import os
import platform
import sys
import unittest
from pathlib import Path

from benchmarks.foundation_scale import ScaleProfile, collect_scale_evidence


class FoundationScaleMemoryPortabilityTests(unittest.TestCase):
    def _profile(self) -> ScaleProfile:
        return ScaleProfile(
            profile_id="tiny-host-memory",
            repo_files=1,
            bytes_per_file=32,
            cycles=1,
            seed=23,
            task="map deterministic scale fixture",
        )

    def test_default_collector_reports_host_peak_rss_and_environment_in_fresh_child(self):
        expected_method = None
        if os.name == "nt":
            expected_method = "windows_get_process_memory_info"
        elif sys.platform == "linux":
            expected_method = "linux_getrusage"
        elif sys.platform == "darwin":
            expected_method = "macos_getrusage"
        if expected_method is None:
            self.skipTest(f"no asserted host peak-RSS probe for {sys.platform}")

        evidence = collect_scale_evidence(
            self._profile(),
            source_commit="1" * 40,
        )
        observation = evidence.observations[0]
        encoded = evidence.as_dict()

        self.assertTrue(observation.completed, observation.error)
        self.assertIsNone(observation.error)
        self.assertIs(type(observation.peak_memory_bytes), int)
        self.assertGreater(observation.peak_memory_bytes, 0)
        self.assertEqual(observation.memory_measurement_method, expected_method)
        self.assertEqual(observation.memory_measurement_scope, "current_process_lifetime")
        self.assertEqual(
            encoded["memory_measurement"],
            "collector_reported_peak_rss",
        )

        environment = encoded["measurement_environment"]
        self.assertEqual(
            environment["schema"],
            "foundation-measurement-environment.v1",
        )
        self.assertEqual(environment["platform_system"], platform.system())
        self.assertEqual(environment["platform_release"], platform.release())
        self.assertEqual(environment["platform_machine"], platform.machine())
        self.assertEqual(environment["python_implementation"], platform.python_implementation())
        self.assertEqual(environment["python_version"], platform.python_version())
        self.assertTrue(
            environment["logical_cpu_count"] is None
            or (
                type(environment["logical_cpu_count"]) is int
                and environment["logical_cpu_count"] > 0
            )
        )
        self.assertRegex(encoded["measurement_environment_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            observation.measurement_environment_fingerprint,
            encoded["measurement_environment_fingerprint"],
        )

    def test_malformed_memory_report_fails_closed_without_inventing_peak(self):
        def malformed(repo: Path, task: str) -> dict:
            return {
                "cold_ingest": {"wall_ms": 1},
                "warm_reconcile": {"wall_ms": 1},
                "orientation": {"wall_ms": 1},
                "process_memory": {
                    "metric": "peak_rss",
                    "unit": "bytes",
                    "scope": "current_process_lifetime",
                    "method": "invalid_fixture_probe",
                    "peak_rss_bytes": 0,
                },
            }

        evidence = collect_scale_evidence(
            self._profile(),
            source_commit="2" * 40,
            collector=malformed,
        )
        observation = evidence.observations[0]

        self.assertFalse(observation.completed)
        self.assertIsNone(observation.peak_memory_bytes)
        self.assertIn("peak_rss_bytes", observation.error or "")
        self.assertEqual(evidence.as_dict()["memory_measurement"], "unavailable")


if __name__ == "__main__":
    unittest.main()

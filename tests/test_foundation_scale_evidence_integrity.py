from __future__ import annotations

import unittest

from benchmarks.foundation_scale import (
    MeasurementEnvironment,
    ScaleEvidence,
    ScaleObservation,
    ScaleProfile,
)


class FoundationScaleEvidenceIntegrityTests(unittest.TestCase):
    def test_completed_observation_must_bind_declared_measurement_environment(self):
        profile = ScaleProfile(
            profile_id="integrity-fixture",
            repo_files=1,
            bytes_per_file=16,
            cycles=1,
            seed=1,
            task="measure integrity fixture",
        )
        environment = MeasurementEnvironment(
            platform_system="Linux",
            platform_release="test-kernel",
            platform_machine="x86_64",
            python_implementation="CPython",
            python_version="3.14.0",
            logical_cpu_count=4,
        )
        observation = ScaleObservation(
            scenario_id="integrity-fixture:0001",
            cycle=1,
            completed=True,
            latency_ms=3.0,
            peak_memory_bytes=1_000_000,
            cold_ingest_ms=1.0,
            warm_reconcile_ms=1.0,
            orientation_ms=1.0,
            memory_measurement_method="test-probe",
            memory_measurement_scope="current_process_lifetime",
            measurement_environment_fingerprint=None,
        )

        with self.assertRaisesRegex(ValueError, "measurement environment"):
            ScaleEvidence(
                source_commit="a" * 40,
                profile=profile,
                workload_fingerprint=profile.workload_fingerprint,
                observations=(observation,),
                measurement_environment=environment,
            )


if __name__ == "__main__":
    unittest.main()

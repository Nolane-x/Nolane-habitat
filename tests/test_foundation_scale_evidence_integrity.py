from __future__ import annotations

import unittest

from benchmarks.foundation_scale import (
    MeasurementEnvironment,
    ScaleEvidence,
    ScaleObservation,
    ScaleProfile,
)


class FoundationScaleEvidenceIntegrityTests(unittest.TestCase):
    def _profile(self) -> ScaleProfile:
        return ScaleProfile(
            profile_id="integrity-fixture",
            repo_files=1,
            bytes_per_file=16,
            cycles=1,
            seed=1,
            task="measure integrity fixture",
        )

    def _environment(self) -> MeasurementEnvironment:
        return MeasurementEnvironment(
            platform_system="Linux",
            platform_release="test-kernel",
            platform_machine="x86_64",
            python_implementation="CPython",
            python_version="3.14.0",
            logical_cpu_count=4,
        )

    def _observation(
        self,
        *,
        environment_fingerprint: str | None,
        scenario_id: str = "integrity-fixture:0001",
        peak_memory_bytes: int | None = 1_000_000,
        memory_method: str | None = "test-probe",
        memory_scope: str | None = "current_process_lifetime",
    ) -> ScaleObservation:
        return ScaleObservation(
            scenario_id=scenario_id,
            cycle=1,
            completed=True,
            latency_ms=3.0,
            peak_memory_bytes=peak_memory_bytes,
            cold_ingest_ms=1.0,
            warm_reconcile_ms=1.0,
            orientation_ms=1.0,
            memory_measurement_method=memory_method,
            memory_measurement_scope=memory_scope,
            measurement_environment_fingerprint=environment_fingerprint,
        )

    def test_completed_observation_must_bind_declared_measurement_environment(self):
        profile = self._profile()
        environment = self._environment()
        observation = self._observation(environment_fingerprint=None)

        with self.assertRaisesRegex(ValueError, "measurement environment"):
            ScaleEvidence(
                source_commit="a" * 40,
                profile=profile,
                workload_fingerprint=profile.workload_fingerprint,
                observations=(observation,),
                measurement_environment=environment,
            )

    def test_peak_memory_requires_explicit_measurement_method_and_scope(self):
        profile = self._profile()
        environment = self._environment()

        with self.assertRaisesRegex(ValueError, "memory measurement"):
            ScaleEvidence(
                source_commit="b" * 40,
                profile=profile,
                workload_fingerprint=profile.workload_fingerprint,
                observations=(
                    self._observation(
                        environment_fingerprint=environment.fingerprint,
                        memory_method=None,
                        memory_scope=None,
                    ),
                ),
                measurement_environment=environment,
            )

    def test_observation_identity_must_match_profile_cycle(self):
        profile = self._profile()
        environment = self._environment()
        observation = self._observation(
            environment_fingerprint=environment.fingerprint,
            scenario_id="different-profile:0001",
        )

        with self.assertRaisesRegex(ValueError, "scenario"):
            ScaleEvidence(
                source_commit="c" * 40,
                profile=profile,
                workload_fingerprint=profile.workload_fingerprint,
                observations=(observation,),
                measurement_environment=environment,
            )


if __name__ == "__main__":
    unittest.main()

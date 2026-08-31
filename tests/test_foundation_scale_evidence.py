from __future__ import annotations

import hashlib
import importlib
import json
import unittest
from pathlib import Path


class FoundationScaleEvidenceTests(unittest.TestCase):
    def _api(self):
        module_path = Path("benchmarks/foundation_scale.py")
        self.assertTrue(
            module_path.is_file(),
            "Deterministic scale evidence producer must exist at benchmarks/foundation_scale.py",
        )
        return importlib.import_module("benchmarks.foundation_scale")

    def _profile(
        self,
        api,
        *,
        profile_id: str = "tiny-deterministic",
        repo_files: int = 4,
        bytes_per_file: int = 128,
        cycles: int = 2,
        seed: int = 17,
    ):
        return api.ScaleProfile(
            profile_id=profile_id,
            repo_files=repo_files,
            bytes_per_file=bytes_per_file,
            cycles=cycles,
            seed=seed,
            task="map deterministic scale fixture",
        )

    @staticmethod
    def _environment(
        *,
        system: str = "Linux",
        release: str = "test-kernel",
        machine: str = "x86_64",
        python_version: str = "3.14.0",
    ) -> dict[str, object]:
        return {
            "schema": "foundation-measurement-environment.v1",
            "platform_system": system,
            "platform_release": release,
            "platform_machine": machine,
            "python_implementation": "CPython",
            "python_version": python_version,
            "logical_cpu_count": 4,
        }

    @staticmethod
    def _collector_factory(
        cold: int,
        warm: int,
        orient: int,
        seen: list[tuple[int, str]],
        *,
        peak_memory_bytes: int | None = None,
        measurement_environment: dict[str, object] | None = None,
    ):
        def collect(repo: Path, task: str):
            files = sorted(path for path in Path(repo).rglob("*") if path.is_file())
            digest = hashlib.sha256()
            for path in files:
                digest.update(path.relative_to(repo).as_posix().encode("utf-8"))
                digest.update(b"\0")
                digest.update(path.read_bytes())
                digest.update(b"\0")
            seen.append((len(files), digest.hexdigest()))
            report = {
                "cold_ingest": {"wall_ms": cold},
                "warm_reconcile": {"wall_ms": warm},
                "orientation": {"wall_ms": orient},
            }
            if peak_memory_bytes is not None:
                report["process_memory"] = {
                    "metric": "peak_rss",
                    "unit": "bytes",
                    "scope": "current_process_lifetime",
                    "method": "test_reported_peak_rss",
                    "peak_rss_bytes": peak_memory_bytes,
                }
            if measurement_environment is not None:
                report["measurement_environment"] = dict(measurement_environment)
            return report

        return collect

    def test_workload_identity_is_deterministic_and_changes_with_workload(self):
        api = self._api()
        left = self._profile(api)
        right = self._profile(api)
        changed = self._profile(api, bytes_per_file=129)

        self.assertEqual(left.workload_fingerprint, right.workload_fingerprint)
        self.assertNotEqual(left.workload_fingerprint, changed.workload_fingerprint)
        self.assertRegex(left.workload_fingerprint, r"^[0-9a-f]{64}$")

    def test_raw_evidence_binds_commit_cycles_and_deterministic_fixture_without_baseline(self):
        api = self._api()
        profile = self._profile(api)
        seen: list[tuple[int, str]] = []
        collector = self._collector_factory(10, 3, 5, seen)

        evidence = api.collect_scale_evidence(
            profile,
            source_commit="a" * 40,
            collector=collector,
        )

        self.assertEqual(evidence.source_commit, "a" * 40)
        self.assertEqual(evidence.workload_fingerprint, profile.workload_fingerprint)
        self.assertEqual(
            [observation.scenario_id for observation in evidence.observations],
            ["tiny-deterministic:0001", "tiny-deterministic:0002"],
        )
        self.assertEqual([observation.latency_ms for observation in evidence.observations], [18.0, 18.0])
        self.assertEqual([observation.peak_memory_bytes for observation in evidence.observations], [None, None])
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(seen[0][0], profile.repo_files)

        encoded = evidence.as_dict()
        self.assertEqual(encoded["schema"], "foundation-scale-evidence.v1")
        self.assertEqual(encoded["source_commit"], "a" * 40)
        self.assertIsNone(encoded["observations"][0]["peak_memory_bytes"])
        self.assertNotIn("baseline_latency_ms", encoded["observations"][0])
        self.assertNotIn("baseline_peak_memory_bytes", encoded["observations"][0])
        self.assertRegex(evidence.evidence_id, r"^[0-9a-f]{64}$")
        self.assertEqual(
            json.loads(evidence.canonical_json())["evidence_id"],
            evidence.evidence_id,
        )

    def test_slo_join_requires_independent_matching_baseline_and_preserves_missing_memory(self):
        api = self._api()
        profile = self._profile(api)
        environment = self._environment()
        current_seen: list[tuple[int, str]] = []
        baseline_seen: list[tuple[int, str]] = []
        current = api.collect_scale_evidence(
            profile,
            source_commit="c" * 40,
            collector=self._collector_factory(
                11,
                4,
                5,
                current_seen,
                measurement_environment=environment,
            ),
        )
        baseline = api.collect_scale_evidence(
            profile,
            source_commit="b" * 40,
            collector=self._collector_factory(
                10,
                3,
                5,
                baseline_seen,
                measurement_environment=environment,
            ),
        )

        samples = api.to_slo_samples(current, baseline)
        self.assertEqual(len(samples), profile.cycles)
        self.assertEqual(samples[0].scenario_id, "tiny-deterministic:0001")
        self.assertEqual(samples[0].latency_ms, 20.0)
        self.assertEqual(samples[0].baseline_latency_ms, 18.0)
        self.assertIsNone(samples[0].peak_memory_bytes)
        self.assertIsNone(samples[0].baseline_peak_memory_bytes)

        with self.assertRaisesRegex(ValueError, "independent"):
            api.to_slo_samples(current, current)
        with self.assertRaisesRegex(ValueError, "baseline"):
            api.to_slo_samples(current, None)

        mismatch = api.collect_scale_evidence(
            self._profile(api, seed=18),
            source_commit="d" * 40,
            collector=self._collector_factory(
                10,
                3,
                5,
                [],
                measurement_environment=environment,
            ),
        )
        with self.assertRaisesRegex(ValueError, "workload"):
            api.to_slo_samples(current, mismatch)

    def test_slo_join_rejects_unknown_or_different_measurement_environment(self):
        api = self._api()
        profile = self._profile(api, cycles=1)
        linux = self._environment(system="Linux", python_version="3.14.0")
        windows = self._environment(
            system="Windows",
            release="test-windows",
            machine="AMD64",
            python_version="3.14.0",
        )
        current = api.collect_scale_evidence(
            profile,
            source_commit="3" * 40,
            collector=self._collector_factory(
                11,
                4,
                5,
                [],
                measurement_environment=linux,
            ),
        )
        same_environment = api.collect_scale_evidence(
            profile,
            source_commit="4" * 40,
            collector=self._collector_factory(
                10,
                3,
                5,
                [],
                measurement_environment=linux,
            ),
        )
        different_environment = api.collect_scale_evidence(
            profile,
            source_commit="5" * 40,
            collector=self._collector_factory(
                10,
                3,
                5,
                [],
                measurement_environment=windows,
            ),
        )
        unknown_environment = api.collect_scale_evidence(
            profile,
            source_commit="6" * 40,
            collector=self._collector_factory(10, 3, 5, []),
        )

        encoded = current.as_dict()
        self.assertEqual(encoded["measurement_environment"], linux)
        self.assertRegex(encoded["measurement_environment_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(api.to_slo_samples(current, same_environment)), 1)
        with self.assertRaisesRegex(ValueError, "environment"):
            api.to_slo_samples(current, different_environment)
        with self.assertRaisesRegex(ValueError, "environment"):
            api.to_slo_samples(current, unknown_environment)

    def test_reported_peak_process_memory_flows_into_scale_and_slo_evidence(self):
        api = self._api()
        profile = self._profile(api, cycles=1)
        environment = self._environment()
        current = api.collect_scale_evidence(
            profile,
            source_commit="e" * 40,
            collector=self._collector_factory(
                12,
                4,
                5,
                [],
                peak_memory_bytes=64_000_000,
                measurement_environment=environment,
            ),
        )
        baseline = api.collect_scale_evidence(
            profile,
            source_commit="f" * 40,
            collector=self._collector_factory(
                10,
                3,
                5,
                [],
                peak_memory_bytes=60_000_000,
                measurement_environment=environment,
            ),
        )

        self.assertEqual(current.observations[0].peak_memory_bytes, 64_000_000)
        self.assertEqual(current.as_dict()["memory_measurement"], "collector_reported_peak_rss")
        samples = api.to_slo_samples(current, baseline)
        self.assertEqual(samples[0].peak_memory_bytes, 64_000_000)
        self.assertEqual(samples[0].baseline_peak_memory_bytes, 60_000_000)

    def test_profile_rejects_non_deterministic_or_degenerate_dimensions(self):
        api = self._api()
        bad_values = (
            {"repo_files": 0},
            {"bytes_per_file": 0},
            {"cycles": 0},
            {"seed": -1},
            {"profile_id": ""},
            {"task": ""},
        )
        for overrides in bad_values:
            kwargs = {
                "profile_id": "tiny",
                "repo_files": 1,
                "bytes_per_file": 16,
                "cycles": 1,
                "seed": 0,
                "task": "scale fixture",
            }
            kwargs.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                api.ScaleProfile(**kwargs)


if __name__ == "__main__":
    unittest.main()

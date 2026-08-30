from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from habitat.backends.base import ExecutionProvider, ExecutionProviderInfo
from habitat.backends.local import BubblewrapExecutionProvider, LocalExecutionProvider
import habitat.execution as execution


_CONTROLS = (
    "process_isolation",
    "filesystem_isolation",
    "network_isolation",
    "user_isolation",
    "capability_drop",
    "resource_limits",
    "secret_boundary",
)


class _FixtureProvider(ExecutionProvider):
    def __init__(self, root: Path):
        self._info = ExecutionProviderInfo(
            provider_id="executor:fixture",
            kind="fixture-provider-v1",
            execution_root=str(root),
            capabilities=("full-sandbox", "filesystem-confinement", "network-confinement"),
        )

    @property
    def info(self) -> ExecutionProviderInfo:
        return self._info

    def discover_capabilities(self) -> list[dict]:
        return []

    def run(self, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None):
        raise NotImplementedError


class ExecutionProviderAttestationTests(unittest.TestCase):
    def _assert_false_controls(self, attestation) -> None:
        for control in _CONTROLS:
            self.assertIs(getattr(attestation, control), False, control)

    def _assert_true_controls_have_success_receipts(self, attestation) -> None:
        successful = {receipt.control for receipt in attestation.probe_receipts if receipt.success}
        for control in _CONTROLS:
            if getattr(attestation, control):
                self.assertIn(control, successful)

    def test_base_provider_fails_closed_instead_of_inferring_from_capability_labels(self):
        with tempfile.TemporaryDirectory() as td:
            provider = _FixtureProvider(Path(td))
            attestation = provider.containment_attestation()

        self.assertEqual("executor:fixture", attestation.provider_id)
        self.assertEqual("fixture-provider-v1", attestation.provider_version)
        self._assert_false_controls(attestation)
        self.assertEqual((), attestation.probe_receipts)
        self.assertIn("not supplied", attestation.claim_boundary)

    def test_trusted_local_provider_is_explicitly_uncontained(self):
        with tempfile.TemporaryDirectory() as td:
            provider = LocalExecutionProvider(Path(td), containment_profile="trusted-local")
            attestation = provider.containment_attestation()

        self.assertEqual(provider.info.provider_id, attestation.provider_id)
        self.assertEqual(provider.info.kind, attestation.provider_version)
        self._assert_false_controls(attestation)
        self.assertIn("trusted", attestation.claim_boundary.lower())

    def test_network_contained_provider_claims_only_mechanically_supported_controls(self):
        namespace_probe = {
            "network_namespace_available": True,
            "user_namespace_available": True,
            "unshare": "/usr/bin/unshare",
            "reason": "user+network namespace launch passed",
        }
        limit_probe = {
            "available": True,
            "mechanism": "posix-rlimit",
            "reason": "strict child resource limits observed",
            "verified_limits": ["nofile", "nproc", "fsize", "core"],
        }
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "habitat.backends.local.containment_probe", return_value=namespace_probe, create=True
        ), mock.patch(
            "habitat.backends.local.resource_limit_probe", return_value=limit_probe, create=True
        ):
            provider = LocalExecutionProvider(Path(td), containment_profile="network-contained")
            attestation = provider.containment_attestation()

        self.assertIs(attestation.process_isolation, False)
        self.assertIs(attestation.filesystem_isolation, False)
        self.assertIs(attestation.network_isolation, True)
        self.assertIs(attestation.user_isolation, True)
        self.assertIs(attestation.capability_drop, False)
        self.assertIs(attestation.resource_limits, True)
        self.assertIs(attestation.secret_boundary, True)
        self._assert_true_controls_have_success_receipts(attestation)

    def test_denied_namespace_probe_never_becomes_network_or_user_proof(self):
        namespace_probe = {
            "network_namespace_available": False,
            "user_namespace_available": False,
            "unshare": "/usr/bin/unshare",
            "reason": "operation not permitted",
        }
        limit_probe = {
            "available": True,
            "mechanism": "posix-rlimit",
            "reason": "strict child resource limits observed",
            "verified_limits": ["nofile", "nproc", "fsize", "core"],
        }
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "habitat.backends.local.containment_probe", return_value=namespace_probe, create=True
        ), mock.patch(
            "habitat.backends.local.resource_limit_probe", return_value=limit_probe, create=True
        ):
            provider = LocalExecutionProvider(Path(td), containment_profile="network-contained")
            attestation = provider.containment_attestation()

        self.assertIs(attestation.network_isolation, False)
        self.assertIs(attestation.user_isolation, False)
        self.assertIs(attestation.filesystem_isolation, False)
        self.assertIs(attestation.process_isolation, False)
        self.assertNotIn(
            "network_isolation",
            {receipt.control for receipt in attestation.probe_receipts if receipt.success},
        )

    def test_bubblewrap_provider_requires_probe_backed_full_control_set(self):
        bwrap_probe = {
            "available": True,
            "executable": "/usr/bin/bwrap",
            "version": "bubblewrap 0.fixture",
            "filesystem_confinement": True,
            "network_confinement": True,
            "pid_namespace": True,
            "user_namespace": True,
            "capabilities_dropped": True,
            "secret_environment_scrubbed": True,
            "reason": "full profile probe passed",
            "claim_boundary": "fixture boundary",
        }
        limit_probe = {
            "available": True,
            "mechanism": "posix-rlimit",
            "reason": "strict child resource limits observed",
            "verified_limits": ["nofile", "nproc", "fsize", "core"],
        }
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "habitat.backends.local.bubblewrap_probe", return_value=bwrap_probe
        ), mock.patch(
            "habitat.backends.local.resource_limit_probe", return_value=limit_probe, create=True
        ):
            provider = BubblewrapExecutionProvider(Path(td))
            attestation = provider.containment_attestation()

        for control in _CONTROLS:
            self.assertIs(getattr(attestation, control), True, control)
        self._assert_true_controls_have_success_receipts(attestation)
        self.assertNotIn("seccomp", " ".join(r.mechanism for r in attestation.probe_receipts).lower())

    def test_bubblewrap_constructor_remains_fail_closed_when_probe_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "habitat.backends.local.bubblewrap_probe",
            return_value={"available": False, "reason": "namespace denied"},
        ):
            with self.assertRaisesRegex(RuntimeError, "bubblewrap sandbox unavailable"):
                BubblewrapExecutionProvider(Path(td))

    def test_resource_limit_probe_verifies_real_child_limits_or_reports_unavailable(self):
        probe = execution.resource_limit_probe()
        self.assertIsInstance(probe, dict)
        self.assertIsInstance(probe.get("available"), bool)
        self.assertTrue(str(probe.get("reason", "")).strip())

        if os.name == "nt" or execution.resource is None:
            self.assertIs(probe["available"], False)
            return

        self.assertIs(probe["available"], True, probe)
        self.assertEqual("posix-rlimit", probe.get("mechanism"))
        verified = set(probe.get("verified_limits") or [])
        self.assertTrue({"nofile", "fsize", "core"}.issubset(verified), probe)
        if hasattr(execution.resource, "RLIMIT_NPROC"):
            self.assertIn("nproc", verified)
        observed = probe.get("observed")
        self.assertIsInstance(observed, dict)
        for name in verified:
            self.assertIn(name, observed)
            self.assertIsInstance(observed[name].get("soft"), int)
            self.assertGreaterEqual(observed[name]["soft"], 0)


if __name__ == "__main__":
    unittest.main()

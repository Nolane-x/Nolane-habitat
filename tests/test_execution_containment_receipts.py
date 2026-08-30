from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from habitat.backends.local import BubblewrapExecutionProvider, LocalExecutionProvider
import habitat.execution as execution
from habitat.model import ExecutionReceipt
from habitat.sandbox import run_bwrap_action
from habitat.security.containment import ContainmentAttestation, ProbeReceipt, unverified_attestation


def _receipt(root: Path, capability: str = "fixture.run") -> ExecutionReceipt:
    return ExecutionReceipt(
        id="run:fixture",
        capability=capability,
        argv=[sys.executable, "-c", "print('ok')"],
        cwd=str(root),
        exit_code=0,
        timed_out=False,
        duration_ms=1,
        stdout="ok\n",
        stderr="",
        environment_fingerprint={},
    )


def _network_attestation(provider_id: str, provider_version: str) -> ContainmentAttestation:
    receipts = (
        ProbeReceipt("probe:network", provider_id, "network_isolation", "linux-unshare-user-network", True, True, "namespace passed"),
        ProbeReceipt("probe:user", provider_id, "user_isolation", "linux-unshare-user-network", True, True, "namespace passed"),
        ProbeReceipt("probe:resource", provider_id, "resource_limits", "posix-rlimit", True, True, "limits passed"),
        ProbeReceipt("probe:secret", provider_id, "secret_boundary", "restricted-environment-allowlist", True, True, "secret boundary passed"),
    )
    return ContainmentAttestation(
        provider_id=provider_id,
        provider_version=provider_version,
        process_isolation=False,
        filesystem_isolation=False,
        network_isolation=True,
        user_isolation=True,
        capability_drop=False,
        resource_limits=True,
        secret_boundary=True,
        probe_receipts=receipts,
        claim_boundary="partial network-contained fixture",
    )


def _bubblewrap_attestation(provider_id: str, provider_version: str, *, resource_limits: bool = True) -> ContainmentAttestation:
    receipts = [
        ProbeReceipt("probe:process", provider_id, "process_isolation", "bubblewrap-pid-namespace", True, True, "passed"),
        ProbeReceipt("probe:filesystem", provider_id, "filesystem_isolation", "bubblewrap-mount-namespace-bind-profile", True, True, "passed"),
        ProbeReceipt("probe:network", provider_id, "network_isolation", "bubblewrap-network-namespace", True, True, "passed"),
        ProbeReceipt("probe:user", provider_id, "user_isolation", "bubblewrap-user-namespace", True, True, "passed"),
        ProbeReceipt("probe:capability", provider_id, "capability_drop", "bubblewrap-cap-drop-all", True, True, "passed"),
        ProbeReceipt("probe:secret", provider_id, "secret_boundary", "bubblewrap-clear-environment", True, True, "passed"),
    ]
    if resource_limits:
        receipts.append(ProbeReceipt("probe:resource", provider_id, "resource_limits", "posix-rlimit", True, True, "passed"))
    return ContainmentAttestation(
        provider_id=provider_id,
        provider_version=provider_version,
        process_isolation=True,
        filesystem_isolation=True,
        network_isolation=True,
        user_isolation=True,
        capability_drop=True,
        resource_limits=resource_limits,
        secret_boundary=True,
        probe_receipts=tuple(receipts),
        claim_boundary="bubblewrap fixture; no custom seccomp or kernel proof",
    )


class ExecutionContainmentReceiptTests(unittest.TestCase):
    def test_trusted_local_actual_run_binds_all_false_typed_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            provider = LocalExecutionProvider(root, containment_profile="trusted-local")
            expected = provider.containment_attestation()
            receipt = provider.run({
                "id": "fixture.run",
                "argv": [sys.executable, "-c", "print('ok')"],
                "kind": "script",
            })

        fp = receipt.environment_fingerprint
        self.assertEqual(expected.as_dict(), fp["containment_attestation"])
        self.assertEqual(expected.fingerprint, fp["containment_attestation_fingerprint"])
        self.assertIs(fp["sandboxed"], False)
        self.assertIs(fp["network_restricted"], False)
        self.assertIs(fp["filesystem_restricted"], False)
        self.assertIs(fp["resource_limited"], False)
        self.assertIs(fp["secret_environment_scrubbed"], False)

    def test_run_action_accepts_explicit_attestation_and_derives_legacy_projection_from_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            attestation = unverified_attestation("executor:fixture", "fixture-v1", "fixture trusted local")
            receipt = execution.run_action(
                root,
                "fixture.run",
                [sys.executable, "-c", "print('ok')"],
                containment_attestation=attestation,
            )

        fp = receipt.environment_fingerprint
        self.assertEqual(attestation.as_dict(), fp["containment_attestation"])
        self.assertEqual(attestation.fingerprint, fp["containment_attestation_fingerprint"])
        self.assertIs(fp["resource_limited"], attestation.resource_limits)
        self.assertIs(fp["secret_environment_scrubbed"], attestation.secret_boundary)

    def test_network_contained_provider_passes_one_exact_attestation_into_the_invocation(self):
        namespace = {
            "network_namespace_available": True,
            "user_namespace_available": True,
            "unshare": "/usr/bin/unshare",
            "reason": "namespace passed",
        }
        limits = {
            "available": True,
            "attempted": True,
            "mechanism": "posix-rlimit",
            "reason": "limits passed",
            "verified_limits": ["nofile", "nproc", "fsize", "core"],
        }
        secrets = {
            "available": True,
            "mechanism": "restricted-environment-allowlist",
            "reason": "secret boundary passed",
        }
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "habitat.backends.local.containment_probe", return_value=namespace
        ), mock.patch(
            "habitat.backends.local.resource_limit_probe", return_value=limits
        ), mock.patch(
            "habitat.backends.local.secret_boundary_probe", return_value=secrets
        ), mock.patch("habitat.backends.local.run_action") as run:
            root = Path(td)
            provider = LocalExecutionProvider(root, containment_profile="network-contained")
            run.return_value = _receipt(root)
            expected = provider.containment_attestation()
            provider.run({"id": "fixture.run", "argv": ["fixture"], "kind": "script"})

        self.assertEqual(1, run.call_count)
        self.assertEqual(run.call_args.kwargs["containment_attestation"], expected)
        self.assertTrue(expected.network_isolation)
        self.assertTrue(expected.user_isolation)
        self.assertTrue(expected.resource_limits)
        self.assertTrue(expected.secret_boundary)
        self.assertFalse(expected.filesystem_isolation)
        self.assertFalse(expected.process_isolation)
        self.assertFalse(expected.capability_drop)

    def test_restricted_environment_is_a_real_child_secret_boundary(self):
        env = dict(os.environ)
        env["HABITAT_API_KEY"] = "wave6-fixture-secret"
        restricted = execution._restricted_env(env)
        proc = subprocess.run(
            [sys.executable, "-c", "import os; print('\\n'.join(sorted(os.environ)))"],
            capture_output=True,
            text=True,
            env=restricted,
            timeout=5,
            shell=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertNotIn("HABITAT_API_KEY", proc.stdout)
        self.assertNotIn("wave6-fixture-secret", proc.stdout)
        self.assertIn("HABITAT_CONTAINED_EXECUTION", proc.stdout)

    def test_bubblewrap_actual_launch_receives_strict_limiter_and_exact_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            attestation = _bubblewrap_attestation("executor:bwrap", "bubblewrap-sandbox")
            capability = {"id": "fixture.run", "argv": ["fixture"], "kind": "script"}
            with mock.patch("habitat.sandbox.build_bwrap_command", return_value=["wrapped"]), mock.patch(
                "habitat.sandbox.run_action", return_value=_receipt(root)
            ) as run:
                receipt = run_bwrap_action(
                    root,
                    capability,
                    containment_attestation=attestation,
                )

        self.assertEqual(1, run.call_count)
        self.assertIs(run.call_args.kwargs["containment_attestation"], attestation)
        self.assertIs(run.call_args.kwargs["apply_resource_limits"], True)
        fp = receipt.environment_fingerprint
        self.assertEqual(attestation.as_dict(), fp["containment_attestation"])
        self.assertEqual(attestation.fingerprint, fp["containment_attestation_fingerprint"])
        self.assertIs(fp["resource_limited"], True)

    def test_bubblewrap_may_not_overclaim_resource_limits_when_attestation_does_not_prove_them(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            attestation = _bubblewrap_attestation("executor:bwrap", "bubblewrap-sandbox", resource_limits=False)
            capability = {"id": "fixture.run", "argv": ["fixture"], "kind": "script"}
            with mock.patch("habitat.sandbox.build_bwrap_command", return_value=["wrapped"]), mock.patch(
                "habitat.sandbox.run_action", return_value=_receipt(root)
            ) as run:
                receipt = run_bwrap_action(
                    root,
                    capability,
                    containment_attestation=attestation,
                )

        self.assertIs(run.call_args.kwargs["apply_resource_limits"], False)
        self.assertIs(receipt.environment_fingerprint["resource_limited"], False)
        self.assertIs(receipt.environment_fingerprint["sandboxed"], True)

    def test_bubblewrap_provider_passes_the_same_attestation_used_for_the_run(self):
        bwrap = {
            "available": True,
            "executable": "/usr/bin/bwrap",
            "version": "bubblewrap fixture",
            "filesystem_confinement": True,
            "network_confinement": True,
            "pid_namespace": True,
            "user_namespace": True,
            "capabilities_dropped": True,
            "secret_environment_scrubbed": True,
            "reason": "passed",
            "claim_boundary": "fixture; no custom seccomp or kernel proof",
        }
        limits = {
            "available": True,
            "attempted": True,
            "mechanism": "posix-rlimit",
            "reason": "passed",
            "verified_limits": ["nofile", "nproc", "fsize", "core"],
        }
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "habitat.backends.local.bubblewrap_probe", return_value=bwrap
        ), mock.patch(
            "habitat.backends.local.resource_limit_probe", return_value=limits
        ), mock.patch("habitat.backends.local.run_bwrap_action") as run:
            root = Path(td)
            provider = BubblewrapExecutionProvider(root)
            run.return_value = _receipt(root)
            expected = provider.containment_attestation()
            provider.run({"id": "fixture.run", "argv": ["fixture"], "kind": "script"})

        self.assertEqual(run.call_args.kwargs["containment_attestation"], expected)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import habitat.execution as execution
from habitat.backends.local import BubblewrapExecutionProvider, LocalExecutionProvider
from habitat.security.capabilities import build_capability_report
from habitat.security.containment import ContainmentAttestation, ProbeReceipt, unverified_attestation


class ExecutionFabricFaultClosureTests(unittest.TestCase):
    def test_true_control_with_only_failed_receipt_is_rejected(self):
        failed = ProbeReceipt(
            receipt_id="probe:failed-network",
            provider_id="executor:fixture",
            control="network_isolation",
            mechanism="fixture-network",
            attempted=True,
            success=False,
            detail="fixture denial",
        )
        with self.assertRaisesRegex(ValueError, "network_isolation"):
            ContainmentAttestation(
                provider_id="executor:fixture",
                provider_version="fixture-v1",
                process_isolation=False,
                filesystem_isolation=False,
                network_isolation=True,
                user_isolation=False,
                capability_drop=False,
                resource_limits=False,
                secret_boundary=False,
                probe_receipts=(failed,),
                claim_boundary="fixture only",
            )

    def test_provider_rejects_attestation_bound_to_another_provider_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            provider = LocalExecutionProvider(Path(td), provider_id="executor:actual")
            forged = unverified_attestation(
                "executor:other",
                "fixture-v1",
                "valid object deliberately bound to another provider",
            )
            capability = {
                "id": "fixture.noop",
                "argv": [sys.executable, "-c", "print('must-not-run')"],
                "kind": "script",
            }
            with patch.object(provider, "containment_attestation", return_value=forged):
                with self.assertRaisesRegex(RuntimeError, "provider.*attestation|attestation.*provider"):
                    provider.run(capability)

    def test_receipt_fingerprint_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            provider = LocalExecutionProvider(Path(td), provider_id="executor:trusted")
            capability = {
                "id": "fixture.noop",
                "argv": [sys.executable, "-c", "print('ok')"],
                "kind": "script",
            }
            receipt = provider.run(capability)
            receipt.environment_fingerprint["containment_attestation_fingerprint"] = "0" * 64

            validator = getattr(execution, "validate_containment_binding")
            with self.assertRaisesRegex(RuntimeError, "fingerprint|containment"):
                validator(receipt, expected_provider_id=provider.info.provider_id)

    def test_capability_labels_cannot_bypass_missing_attestation(self):
        report = build_capability_report(
            source_authority={"authority_id": "source:fixture", "capabilities": []},
            execution_provider={
                "provider_id": "executor:labels-only",
                "capabilities": [
                    "full-sandbox",
                    "filesystem-confinement",
                    "network-confinement",
                    "pid-namespace",
                ],
            },
            generated_at_revision="revision",
        )
        self.assertFalse(report.execution.sandboxed)
        self.assertFalse(report.execution.network_restricted)
        self.assertFalse(report.execution.filesystem_restricted)
        self.assertFalse(report.execution.process_isolated)

    def test_bubblewrap_unavailable_still_fails_provider_construction_closed(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "habitat.backends.local.bubblewrap_probe",
            return_value={"available": False, "reason": "fixture denied"},
        ):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                BubblewrapExecutionProvider(Path(td), provider_id="executor:bwrap")

    def test_trusted_local_remains_executable_without_sandbox_claims(self):
        with tempfile.TemporaryDirectory() as td:
            provider = LocalExecutionProvider(Path(td), provider_id="executor:trusted")
            capability = {
                "id": "fixture.echo",
                "argv": [sys.executable, "-c", "print('trusted-local-ok')"],
                "kind": "script",
            }
            receipt = provider.run(capability)
            fp = receipt.environment_fingerprint
            self.assertEqual(0, receipt.exit_code)
            self.assertIn("trusted-local-ok", receipt.stdout)
            self.assertFalse(fp["sandboxed"])
            self.assertFalse(fp["network_restricted"])
            self.assertFalse(fp["filesystem_restricted"])
            self.assertFalse(fp["process_isolated"])

    def test_bubblewrap_claim_boundary_excludes_universal_safety_claims(self):
        probe = {
            "available": True,
            "executable": "/usr/bin/bwrap",
            "version": "fixture",
            "filesystem_confinement": True,
            "network_confinement": True,
            "pid_namespace": True,
            "user_namespace": True,
            "capabilities_dropped": True,
            "secret_environment_scrubbed": True,
            "reason": "fixture primitive proof",
            "claim_boundary": "Probe covers namespace/mount/cap-drop/clear-env primitives; it is not a proof against kernel/runtime or Bubblewrap vulnerabilities and no Habitat custom seccomp filter is installed.",
        }
        limits = {
            "available": True,
            "attempted": True,
            "mechanism": "posix-rlimit",
            "reason": "fixture resource proof",
        }
        with tempfile.TemporaryDirectory() as td, patch(
            "habitat.backends.local.bubblewrap_probe", return_value=probe
        ), patch("habitat.backends.local.resource_limit_probe", return_value=limits):
            provider = BubblewrapExecutionProvider(Path(td), provider_id="executor:bwrap")
            attestation = provider.containment_attestation()

        boundary = attestation.claim_boundary.lower()
        self.assertIn("no habitat custom seccomp", boundary)
        self.assertIn("kernel/runtime", boundary)
        serialized = str(attestation.as_dict()).lower()
        self.assertNotIn("microvm", serialized)
        self.assertNotIn("hostile_code_safe", serialized)
        self.assertNotIn("universally safe", serialized)


if __name__ == "__main__":
    unittest.main()

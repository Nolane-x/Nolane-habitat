from __future__ import annotations

from dataclasses import FrozenInstanceError
import re
import unittest

from habitat.security.containment import (
    CONTAINMENT_CONTROLS,
    ContainmentAttestation,
    ProbeReceipt,
    unverified_attestation,
)


EXPECTED_CONTROLS = (
    "process_isolation",
    "filesystem_isolation",
    "network_isolation",
    "user_isolation",
    "capability_drop",
    "resource_limits",
    "secret_boundary",
)


def receipt(
    control: str,
    *,
    receipt_id: str | None = None,
    provider_id: str = "executor:fixture",
    attempted: bool = True,
    success: bool = True,
    mechanism: str | None = None,
    detail: str | None = None,
) -> ProbeReceipt:
    return ProbeReceipt(
        receipt_id=receipt_id or f"probe:{control}:1",
        provider_id=provider_id,
        control=control,
        mechanism=mechanism or f"fixture-{control}",
        attempted=attempted,
        success=success,
        detail=detail or f"fixture evidence for {control}",
    )


def attestation(**overrides) -> ContainmentAttestation:
    values = {
        "provider_id": "executor:fixture",
        "provider_version": "fixture-v1",
        "process_isolation": False,
        "filesystem_isolation": False,
        "network_isolation": True,
        "user_isolation": True,
        "capability_drop": False,
        "resource_limits": False,
        "secret_boundary": False,
        "probe_receipts": (
            receipt("network_isolation"),
            receipt("user_isolation"),
        ),
        "claim_boundary": "fixture containment evidence only",
    }
    values.update(overrides)
    return ContainmentAttestation(**values)


class ProbeReceiptTests(unittest.TestCase):
    def test_exact_control_taxonomy_is_stable(self):
        self.assertEqual(EXPECTED_CONTROLS, CONTAINMENT_CONTROLS)

    def test_receipt_is_frozen_and_rejects_unknown_or_empty_identity(self):
        value = receipt("network_isolation")
        with self.assertRaises(FrozenInstanceError):
            value.success = False

        for field in ("receipt_id", "provider_id", "mechanism", "detail"):
            kwargs = {field: "   "}
            with self.subTest(field=field), self.assertRaises(ValueError):
                ProbeReceipt(
                    receipt_id=kwargs.get("receipt_id", "probe:1"),
                    provider_id=kwargs.get("provider_id", "executor:fixture"),
                    control="network_isolation",
                    mechanism=kwargs.get("mechanism", "fixture"),
                    attempted=True,
                    success=True,
                    detail=kwargs.get("detail", "passed"),
                )

        with self.assertRaisesRegex(ValueError, "unknown containment control"):
            receipt("microvm_magic")

    def test_success_requires_an_attempted_probe_and_real_booleans(self):
        with self.assertRaisesRegex(ValueError, "attempted"):
            receipt("network_isolation", attempted=False, success=True)
        with self.assertRaises(TypeError):
            ProbeReceipt(
                receipt_id="probe:1",
                provider_id="executor:fixture",
                control="network_isolation",
                mechanism="fixture",
                attempted=1,
                success=True,
                detail="invalid bool",
            )
        with self.assertRaises(TypeError):
            ProbeReceipt(
                receipt_id="probe:1",
                provider_id="executor:fixture",
                control="network_isolation",
                mechanism="fixture",
                attempted=True,
                success=1,
                detail="invalid bool",
            )


class ContainmentAttestationTests(unittest.TestCase):
    def test_attestation_is_frozen_and_accepts_exact_evidence(self):
        value = attestation()
        self.assertTrue(value.network_isolation)
        self.assertTrue(value.user_isolation)
        self.assertFalse(value.filesystem_isolation)
        with self.assertRaises(FrozenInstanceError):
            value.network_isolation = False

    def test_every_true_control_requires_successful_same_provider_receipt(self):
        with self.assertRaisesRegex(ValueError, "network_isolation"):
            attestation(
                probe_receipts=(
                    receipt("network_isolation", success=False),
                    receipt("user_isolation"),
                )
            )

        with self.assertRaisesRegex(ValueError, "provider"):
            attestation(
                probe_receipts=(
                    receipt("network_isolation", provider_id="executor:other"),
                    receipt("user_isolation"),
                )
            )

        with self.assertRaisesRegex(ValueError, "filesystem_isolation"):
            attestation(filesystem_isolation=True)

    def test_duplicate_receipt_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            attestation(
                probe_receipts=(
                    receipt("network_isolation", receipt_id="probe:duplicate"),
                    receipt("user_isolation", receipt_id="probe:duplicate"),
                )
            )

    def test_attestation_rejects_empty_identity_and_non_boolean_controls(self):
        for field in ("provider_id", "provider_version", "claim_boundary"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                attestation(**{field: "   "})

        with self.assertRaises(TypeError):
            attestation(network_isolation=1)

    def test_serialization_is_json_compatible_and_deterministic(self):
        value = attestation()
        first = value.as_dict()
        second = attestation().as_dict()
        self.assertEqual(first, second)
        self.assertIsInstance(first["probe_receipts"], list)
        self.assertEqual(
            ["network_isolation", "user_isolation"],
            [item["control"] for item in first["probe_receipts"]],
        )
        self.assertEqual("executor:fixture", first["provider_id"])
        self.assertEqual("fixture-v1", first["provider_version"])

    def test_fingerprint_binds_all_security_evidence(self):
        base = attestation()
        self.assertRegex(base.fingerprint, re.compile(r"^[0-9a-f]{64}$"))

        variants = (
            attestation(provider_version="fixture-v2"),
            attestation(claim_boundary="different boundary"),
            attestation(
                network_isolation=False,
                probe_receipts=(receipt("user_isolation"),),
            ),
            attestation(
                probe_receipts=(
                    receipt("network_isolation", detail="different evidence"),
                    receipt("user_isolation"),
                )
            ),
        )
        for variant in variants:
            with self.subTest(fingerprint=variant.fingerprint):
                self.assertNotEqual(base.fingerprint, variant.fingerprint)

    def test_unverified_attestation_is_explicitly_all_false(self):
        value = unverified_attestation(
            "executor:custom",
            "custom-v1",
            "custom provider has no containment proof",
        )
        self.assertEqual("executor:custom", value.provider_id)
        self.assertEqual((), value.probe_receipts)
        for control in CONTAINMENT_CONTROLS:
            with self.subTest(control=control):
                self.assertFalse(getattr(value, control))


if __name__ == "__main__":
    unittest.main()

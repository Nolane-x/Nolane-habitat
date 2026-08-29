from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from habitat.operation_registry import OperationDescriptor, OperationRegistry


def _handler(_protocol, _params):
    return {"ok": True}


class OperationRegistryKernelTests(unittest.TestCase):
    def test_descriptor_is_frozen(self):
        descriptor = OperationDescriptor("alpha", _handler, read_only=True)

        with self.assertRaises(FrozenInstanceError):
            descriptor.name = "beta"

    def test_registry_preserves_insertion_order(self):
        first = OperationDescriptor("first", _handler)
        second = OperationDescriptor("second", _handler, read_only=True)
        registry = OperationRegistry((first, second))

        self.assertEqual(("first", "second"), registry.names)
        self.assertIs(first, registry.get("first"))
        self.assertIs(second, registry.get("second"))
        self.assertIsNone(registry.get("missing"))

    def test_duplicate_names_fail_deterministically(self):
        with self.assertRaisesRegex(ValueError, "duplicate operation: duplicate"):
            OperationRegistry(
                (
                    OperationDescriptor("duplicate", _handler),
                    OperationDescriptor("duplicate", _handler),
                )
            )

    def test_names_and_read_only_names_are_immutable(self):
        registry = OperationRegistry(
            (
                OperationDescriptor("read", _handler, read_only=True),
                OperationDescriptor("write", _handler),
            )
        )

        self.assertIsInstance(registry.names, tuple)
        self.assertEqual(frozenset({"read"}), registry.read_only_names)
        with self.assertRaises(AttributeError):
            registry.names.append("other")
        with self.assertRaises(AttributeError):
            registry.read_only_names.add("write")

    def test_registry_has_no_runtime_registration_api(self):
        registry = OperationRegistry((OperationDescriptor("only", _handler),))

        self.assertFalse(hasattr(registry, "register"))
        self.assertFalse(hasattr(registry, "add"))
        self.assertFalse(hasattr(registry, "remove"))
        self.assertFalse(hasattr(registry, "clear"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest
from unittest import mock

from habitat.operation_registry import (
    OPERATION_REGISTRY,
    OperationDescriptor,
    OperationRegistry,
)


def _handler(_protocol, _params):
    return {"ok": True}


EXPECTED_METHODS = (
    "protocol.capabilities",
    "workspace.enter",
    "workspace.refresh",
    "workspace.orient",
    "workspace.explore",
    "workspace.context.page",
    "workspace.context.refresh",
    "workspace.query",
    "workspace.inspect",
    "workspace.inspect.batch",
    "workspace.context.materialize",
    "workspace.context.address_space",
    "workspace.context.fetch",
    "workspace.context.prefetch",
    "workspace.context.plan_next",
    "workspace.context.feedback",
    "workspace.context.efficiency",
    "workspace.references",
    "workspace.impact",
    "workspace.source.read",
    "workspace.change.plan",
    "workspace.change.stage",
    "workspace.change.stage_symbol",
    "workspace.change.stage_rename_symbol",
    "workspace.change.commit",
    "workspace.change.rollback",
    "workspace.verification.plan",
    "workspace.verification.run",
    "workspace.events.poll",
    "workspace.diff.since",
    "workspace.state.merkle",
    "workspace.state.merkle.diff",
    "workspace.watch.start",
    "workspace.watch.poll",
    "workspace.watch.wait",
    "workspace.watch.status",
    "workspace.watch.stop",
    "workspace.backend.info",
    "workspace.semantic.providers",
    "workspace.semantic.fabric",
    "workspace.evidence.active",
    "workspace.episode.start",
    "workspace.episode.status",
    "workspace.episode.finish",
    "workspace.episode.efficiency",
    "workspace.invariant.create",
    "workspace.invariant.status",
    "workspace.invariant.link",
    "workspace.invariant.update",
    "workspace.hypothesis.create",
    "workspace.hypothesis.status",
    "workspace.hypothesis.link_evidence",
    "workspace.hypothesis.update",
    "workspace.hypothesis.compare",
    "workspace.hypothesis.next_experiment",
    "workspace.agent.belief.update",
    "workspace.agent.belief.status",
    "workspace.agent.belief.portfolio",
    "workspace.experiment.plan",
    "workspace.experiment.status",
    "workspace.experiment.complete",
    "workspace.causality.explain",
    "workspace.causality.graph",
    "workspace.checkpoint",
    "workspace.resume",
    "workspace.context.residency.configure",
    "workspace.context.residency.admit",
    "workspace.context.residency.status",
    "workspace.context.residency.materialize",
    "workspace.context.residency.touch",
    "workspace.context.residency.pin",
    "workspace.context.residency.evict",
    "workspace.trace.start",
    "workspace.trace.status",
    "workspace.trace.stop",
    "workspace.activity.since",
    "workspace.observatory.start",
    "workspace.observatory.status",
    "workspace.observatory.stop",
    "workspace.epistemic.create",
    "workspace.epistemic.state",
    "workspace.epistemic.update",
    "workspace.cognition.next",
    "workspace.cognition.probe_unknowns",
    "workspace.cognition.plan",
    "workspace.cognition.health",
    "workspace.executive.start",
    "workspace.executive.status",
    "workspace.executive.plan",
    "workspace.executive.advance",
    "workspace.executive.milestone.add",
    "workspace.executive.milestone.update",
    "workspace.executive.complete",
    "workspace.executive.stop",
    "workspace.project.world",
    "workspace.effect.refresh",
    "workspace.effect.snapshot",
    "workspace.dataflow.refresh",
    "workspace.dataflow.snapshot",
    "workspace.runtime.topology",
    "workspace.counterfactual.fork",
    "workspace.counterfactual.status",
    "workspace.counterfactual.apply",
    "workspace.counterfactual.evaluate",
    "workspace.counterfactual.compare",
    "workspace.counterfactual.verify",
    "workspace.counterfactual.promote",
    "workspace.counterfactual.discard",
    "workspace.memory.record",
    "workspace.memory.status",
    "workspace.memory.recall",
    "workspace.memory.invalidate",
    "workspace.runtime.ingest",
    "workspace.runtime.timeline",
    "workspace.policy.status",
    "workspace.policy.update",
    "workspace.policy.evaluate",
    "workspace.execution.security",
    "workspace.execution.configure",
    "workspace.sandbox.status",
    "workspace.retention.status",
    "workspace.retention.compact",
    "workspace.state.security",
    "workspace.world.summary",
    "workspace.world.health",
    "workspace.guidance.discover",
    "workspace.guidance.read",
    "workspace.git.status",
    "workspace.git.history",
    "workspace.git.blame",
    "workspace.git.explain_line",
    "workspace.git.diff",
    "workspace.git.changed_files",
    "workspace.git.churn",
    "workspace.git.explain_symbol",
    "workspace.git.branches",
    "workspace.git.worktrees",
    "workspace.git.conflicts",
    "workspace.git.commit_impact",
    "workspace.dependencies.snapshot",
    "workspace.dependencies.query",
    "workspace.dependencies.world",
    "workspace.agent.open",
    "workspace.agent.status",
    "workspace.agent.close",
    "workspace.agent.observe",
    "workspace.agent.notifications",
    "workspace.agent.notifications.ack",
    "workspace.agent.revalidate",
    "workspace.agent.residency.admit",
    "workspace.agent.residency.status",
    "workspace.agent.residency.evict",
    "workspace.lease.acquire",
    "workspace.lease.release",
    "workspace.lease.status",
    "action.run",
    "ui.observe",
    "ui.runtime.open",
    "ui.runtime.observe",
    "ui.runtime.act",
    "ui.runtime.assert",
    "ui.runtime.close",
)

EXPECTED_READ_ONLY = frozenset((
    "protocol.capabilities",
    "workspace.inspect",
    "workspace.inspect.batch",
    "workspace.references",
    "workspace.source.read",
))


class _TelemetryWorkspace:
    revision = "telemetry-revision"

    def __init__(self):
        self.activity = []
        self.trace_calls = []

    def activity_emit(self, event, *args, **kwargs):
        self.activity.append((event, args, kwargs))

    def record_trace_call(self, *args):
        self.trace_calls.append(args)

    def inspect_snapshot(self, object_id, include_source):
        return {"object_id": object_id, "include_source": include_source}

    def inspect_many(self, object_ids, include_source, max_objects):
        return {"object_ids": object_ids, "include_source": include_source, "max_objects": max_objects}

    def references_snapshot(self, object_id, limit):
        return {"object_id": object_id, "limit": limit}

    def read_source(self, path, start_line, max_lines):
        return {"path": path, "start_line": start_line, "max_lines": max_lines}

    def watch_status(self):
        return {"running": False}

    def activity_since(self, since_seq, limit):
        return {"since_seq": since_seq, "limit": limit}

    def observatory_status(self):
        return {"running": False}

    def trace_status(self, trace_id):
        return {"trace_id": trace_id, "running": False}


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


class OperationRegistrySurfaceTests(unittest.TestCase):
    def test_expected_surface_is_explicitly_complete_and_unique(self):
        self.assertEqual(162, len(EXPECTED_METHODS))
        self.assertEqual(162, len(set(EXPECTED_METHODS)))
        self.assertEqual(5, len(EXPECTED_READ_ONLY))

    def test_static_registry_preserves_exact_legacy_method_order(self):
        self.assertEqual(EXPECTED_METHODS, OPERATION_REGISTRY.names)

    def test_static_registry_preserves_exact_read_only_classification(self):
        self.assertEqual(EXPECTED_READ_ONLY, OPERATION_REGISTRY.read_only_names)

    def test_static_registry_has_exactly_one_callable_handler_per_method(self):
        descriptors = tuple(OPERATION_REGISTRY.get(name) for name in EXPECTED_METHODS)

        self.assertTrue(all(descriptor is not None for descriptor in descriptors))
        self.assertEqual(
            EXPECTED_METHODS,
            tuple(descriptor.name for descriptor in descriptors if descriptor is not None),
        )
        self.assertTrue(
            all(
                callable(descriptor.handler)
                for descriptor in descriptors
                if descriptor is not None
            )
        )

    def test_static_registry_construction_does_not_require_a_workspace(self):
        self.assertEqual(EXPECTED_METHODS, OPERATION_REGISTRY.names)
        self.assertTrue(
            all(
                getattr(OPERATION_REGISTRY.get(name).handler, "__self__", None) is None
                for name in EXPECTED_METHODS
            )
        )


class ProtocolRegistryRoutingTests(unittest.TestCase):
    def test_protocol_public_projections_match_registry_contract(self):
        from habitat.protocol import HabitatProtocol

        self.assertIsInstance(HabitatProtocol.METHODS, list)
        self.assertEqual(list(OPERATION_REGISTRY.names), HabitatProtocol.METHODS)
        self.assertEqual(OPERATION_REGISTRY.read_only_names, HabitatProtocol.READ_ONLY_METHODS)

    def test_dispatch_delegates_through_registry_handler_seam(self):
        from habitat import protocol as protocol_module

        calls = []

        def handler(protocol, params):
            calls.append((protocol, params))
            return {"routed": params["value"]}

        registry = OperationRegistry((OperationDescriptor("test.route", handler),))
        protocol = protocol_module.HabitatProtocol(object())

        with mock.patch.object(protocol_module, "OPERATION_REGISTRY", registry):
            result = protocol._dispatch("test.route", {"value": 7})

        self.assertEqual({"routed": 7}, result)
        self.assertEqual([(protocol, {"value": 7})], calls)

    def test_unknown_dispatch_preserves_exact_key_error_contract(self):
        from habitat.protocol import HabitatProtocol

        protocol = HabitatProtocol(object())
        with self.assertRaises(KeyError) as raised:
            protocol._dispatch("missing.operation", {})

        self.assertEqual(("unknown method: missing.operation",), raised.exception.args)

    def test_capabilities_preserve_exact_registry_order_and_list_shape(self):
        from habitat.protocol import HabitatProtocol

        result = HabitatProtocol(object())._dispatch("protocol.capabilities", {})

        self.assertEqual("habitat.agent.v1alpha2", result["protocol"])
        self.assertEqual(list(EXPECTED_METHODS), result["methods"])
        self.assertIsInstance(result["methods"], list)
        self.assertFalse(result["generic_shell"])


class ProtocolRegistryTelemetryTests(unittest.TestCase):
    @staticmethod
    def _call(method, params=None):
        from habitat.protocol import HabitatProtocol

        workspace = _TelemetryWorkspace()
        response = HabitatProtocol(workspace).handle(
            {"id": "telemetry-test", "method": method, "params": params or {}}
        )
        return workspace, response

    def test_read_only_telemetry_uses_registry_metadata_not_compatibility_projection(self):
        from habitat.protocol import HabitatProtocol

        cases = {
            "protocol.capabilities": {},
            "workspace.inspect": {"object_id": "object-1"},
            "workspace.inspect.batch": {"object_ids": ["object-1"]},
            "workspace.references": {"object_id": "object-1"},
            "workspace.source.read": {"path": "module.py"},
        }
        self.assertEqual(EXPECTED_READ_ONLY, OPERATION_REGISTRY.read_only_names)

        with mock.patch.object(HabitatProtocol, "READ_ONLY_METHODS", frozenset()):
            for method, params in cases.items():
                with self.subTest(method=method):
                    workspace, response = self._call(method, params)
                    self.assertTrue(response["ok"])
                    self.assertEqual([], workspace.activity)
                    self.assertEqual([], workspace.trace_calls)

    def test_ordinary_operation_retains_activity_and_trace_telemetry(self):
        workspace, response = self._call("workspace.watch.status")

        self.assertTrue(response["ok"])
        self.assertEqual(["tool.started", "tool.completed"], [item[0] for item in workspace.activity])
        self.assertEqual(1, len(workspace.trace_calls))
        self.assertEqual("workspace.watch.status", workspace.trace_calls[0][0])
        self.assertTrue(workspace.trace_calls[0][1])

    def test_activity_and_observatory_operations_keep_activity_exclusion_but_trace(self):
        for method in ("workspace.activity.since", "workspace.observatory.status"):
            with self.subTest(method=method):
                workspace, response = self._call(method)
                self.assertTrue(response["ok"])
                self.assertEqual([], workspace.activity)
                self.assertEqual(1, len(workspace.trace_calls))
                self.assertEqual(method, workspace.trace_calls[0][0])

    def test_trace_control_operations_keep_both_activity_and_trace_exclusions(self):
        workspace, response = self._call("workspace.trace.status")

        self.assertTrue(response["ok"])
        self.assertEqual([], workspace.activity)
        self.assertEqual([], workspace.trace_calls)

    def test_unknown_operation_retains_legacy_failed_activity_and_trace_behavior(self):
        workspace, response = self._call("missing.operation")

        self.assertFalse(response["ok"])
        self.assertEqual("NOT_FOUND", response["error"]["code"])
        self.assertEqual(["tool.started", "tool.completed"], [item[0] for item in workspace.activity])
        self.assertEqual(1, len(workspace.trace_calls))
        self.assertEqual("missing.operation", workspace.trace_calls[0][0])
        self.assertFalse(workspace.trace_calls[0][1])


if __name__ == "__main__":
    unittest.main()

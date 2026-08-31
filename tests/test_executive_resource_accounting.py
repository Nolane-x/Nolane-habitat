from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace


class ExecutiveResourceAccountingTests(unittest.TestCase):
    def make_ws(self):
        td = tempfile.TemporaryDirectory()
        base = Path(td.name)
        project = base / "project"
        project.mkdir()
        (project / "app.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        ws = HabitatWorkspace.create(project, base / "habitat")
        return td, ws

    @staticmethod
    def usage(receipt_id: str = "receipt-1", **overrides):
        value = {
            "provider_id": "provider-A",
            "receipt_id": receipt_id,
            "tool_calls": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "compute_ms": 20,
        }
        value.update(overrides)
        return value

    def test_provider_metered_budget_requires_usage_before_mutation(self):
        td, ws = self.make_ws()
        try:
            tr = ws.executive_start("Bound provider work", budget={"max_tool_calls": 1})
            before = ws.executive_status(tr["id"])
            with self.assertRaises(ValueError):
                ws.executive_advance(tr["id"], "UPDATE", "update world", status="passed", progress=True)
            after = ws.executive_status(tr["id"])
            self.assertEqual(after["event_count"], before["event_count"])
            self.assertEqual(after["metrics"], before["metrics"])
        finally:
            ws.close()
            td.cleanup()

    def test_provider_usage_is_event_derived_and_exhausts_declared_limits(self):
        td, ws = self.make_ws()
        try:
            tr = ws.executive_start(
                "Bound provider work",
                budget={
                    "max_tool_calls": 1,
                    "max_input_tokens": 10,
                    "max_output_tokens": 5,
                    "max_compute_ms": 20,
                },
            )
            ws.executive_advance(
                tr["id"],
                "UPDATE",
                "provider-backed update",
                status="passed",
                progress=True,
                data={"resource_usage": self.usage()},
            )
            state = ws.executive_status(tr["id"])["budget_state"]
            consumed = state["consumed"]
            accounting = state.get("accounting") or {}
            self.assertEqual(consumed.get("tool_calls"), 1)
            self.assertEqual(consumed.get("input_tokens"), 10)
            self.assertEqual(consumed.get("output_tokens"), 5)
            self.assertEqual(consumed.get("compute_ms"), 20)
            self.assertEqual(accounting.get("provider_usage"), "provider-reported-hash-chained")
            self.assertEqual(accounting.get("receipt_count"), 1)
            self.assertTrue(accounting.get("provider_usage_required"))
            self.assertTrue(state["exhausted"])
            self.assertEqual(
                set(state["reasons"]),
                {
                    "TOOL_CALL_BUDGET_EXHAUSTED",
                    "INPUT_TOKEN_BUDGET_EXHAUSTED",
                    "OUTPUT_TOKEN_BUDGET_EXHAUSTED",
                    "COMPUTE_BUDGET_EXHAUSTED",
                },
            )
            self.assertNotIn("max_tool_calls", state["unmetered"])
            self.assertNotIn("max_input_tokens", state["unmetered"])
            self.assertNotIn("max_output_tokens", state["unmetered"])
            self.assertNotIn("max_compute_ms", state["unmetered"])
        finally:
            ws.close()
            td.cleanup()

    def test_invalid_provider_usage_fails_before_event_mutation(self):
        cases = [
            {"provider_id": "", "receipt_id": "r", "tool_calls": 1},
            {"provider_id": "p", "receipt_id": "", "tool_calls": 1},
            {"provider_id": "p", "receipt_id": "r", "tool_calls": -1},
            {"provider_id": "p", "receipt_id": "r", "tool_calls": True},
            {"provider_id": "p", "receipt_id": "r", "mystery_units": 1},
            {"provider_id": "p", "receipt_id": "r"},
        ]
        for index, usage in enumerate(cases):
            with self.subTest(index=index, usage=usage):
                td, ws = self.make_ws()
                try:
                    tr = ws.executive_start("Validate provider usage", budget={"max_tool_calls": 3})
                    before = ws.executive_status(tr["id"])["event_count"]
                    with self.assertRaises((TypeError, ValueError)):
                        ws.executive_advance(
                            tr["id"],
                            "UPDATE",
                            "invalid usage",
                            status="passed",
                            data={"resource_usage": usage},
                        )
                    self.assertEqual(ws.executive_status(tr["id"])["event_count"], before)
                finally:
                    ws.close()
                    td.cleanup()

    def test_duplicate_provider_receipt_is_rejected_without_double_counting(self):
        td, ws = self.make_ws()
        try:
            tr = ws.executive_start("Reject replay", budget={"max_tool_calls": 3})
            ws.executive_advance(
                tr["id"],
                "UPDATE",
                "first accounted step",
                status="passed",
                data={"resource_usage": self.usage("receipt-replay", input_tokens=0, output_tokens=0, compute_ms=0)},
            )
            before = ws.executive_status(tr["id"])
            with self.assertRaises(ValueError):
                ws.executive_advance(
                    tr["id"],
                    "DIAGNOSE",
                    "replayed receipt",
                    status="passed",
                    data={"resource_usage": self.usage("receipt-replay", input_tokens=0, output_tokens=0, compute_ms=0)},
                )
            after = ws.executive_status(tr["id"])
            self.assertEqual(after["event_count"], before["event_count"])
            self.assertEqual(after["budget_state"]["consumed"].get("tool_calls"), 1)
        finally:
            ws.close()
            td.cleanup()

    def test_wall_time_is_habitat_measured_and_hard_enforced(self):
        td, ws = self.make_ws()
        try:
            with mock.patch("habitat._workspace_core.time.time_ns", return_value=1_000_000_000):
                tr = ws.executive_start("Bound wall time", budget={"max_wall_time_ms": 1})
            with mock.patch("habitat._workspace_core.time.time_ns", return_value=1_002_000_000):
                state = ws.executive_status(tr["id"])["budget_state"]
                self.assertEqual(state["consumed"].get("wall_time_ms"), 2)
                self.assertEqual((state.get("accounting") or {}).get("wall_time"), "habitat-measured-host-wall-clock")
                self.assertIn("WALL_TIME_BUDGET_EXHAUSTED", state["reasons"])
                with self.assertRaises(RuntimeError):
                    ws.executive_advance(tr["id"], "UPDATE", "too late", status="passed")
        finally:
            ws.close()
            td.cleanup()

    def test_unknown_budget_keys_remain_explicitly_unmetered(self):
        td, ws = self.make_ws()
        try:
            tr = ws.executive_start("Preserve historical extension", budget={"max_custom_units": 7})
            state = ws.executive_status(tr["id"])["budget_state"]
            self.assertEqual(state["unmetered"], {"max_custom_units": 7})
        finally:
            ws.close()
            td.cleanup()

    def test_historical_step_budget_behavior_remains_compatible(self):
        td, ws = self.make_ws()
        try:
            tr = ws.executive_start("Historical budget", budget={"max_steps": 1})
            ws.executive_advance(tr["id"], "UPDATE", "one step", status="passed", progress=True)
            state = ws.executive_plan(tr["id"])["budget"]
            self.assertTrue(state["exhausted"])
            self.assertIn("STEP_BUDGET_EXHAUSTED", state["reasons"])
        finally:
            ws.close()
            td.cleanup()

    def test_resource_usage_is_part_of_tamper_evident_event_chain(self):
        td, ws = self.make_ws()
        try:
            tr = ws.executive_start("Hash accounting", budget={"max_tool_calls": 2})
            ws.executive_advance(
                tr["id"],
                "UPDATE",
                "accounted step",
                status="passed",
                data={"resource_usage": self.usage(input_tokens=0, output_tokens=0, compute_ms=0)},
            )
            row = ws.store.conn.execute(
                "SELECT ordinal FROM executive_events WHERE trajectory_id=? AND operation='accounted step'",
                (tr["id"],),
            ).fetchone()
            self.assertIsNotNone(row)
            ws.store.conn.execute(
                "UPDATE executive_events SET data_json=? WHERE trajectory_id=? AND ordinal=?",
                (json.dumps({"control_step": True, "resource_usage": {"provider_id": "provider-A", "receipt_id": "receipt-1", "tool_calls": 2}}), tr["id"], row["ordinal"]),
            )
            ws.store.conn.commit()
            self.assertFalse(ws.executive_status(tr["id"])["trajectory_chain"]["valid"])
        finally:
            ws.close()
            td.cleanup()

    def test_alpha19_protocol_catalog_is_unchanged_and_existing_advance_carries_data(self):
        td, ws = self.make_ws()
        try:
            proto = HabitatProtocol(ws)
            methods = proto.handle({"id": "caps", "method": "protocol.capabilities", "params": {}})["result"]["methods"]
            self.assertIn("workspace.executive.advance", methods)
            self.assertNotIn("workspace.executive.usage.record", methods)
        finally:
            ws.close()
            td.cleanup()

    def test_current_resource_accounting_trajectory_remains_schema_valid(self):
        td, ws = self.make_ws()
        try:
            tr = ws.executive_start("Schema accounting", budget={"max_tool_calls": 2})
            ws.executive_advance(
                tr["id"],
                "UPDATE",
                "accounted step",
                status="passed",
                data={"resource_usage": self.usage(input_tokens=0, output_tokens=0, compute_ms=0)},
            )
            schema = json.loads((Path(__file__).parents[1] / "schemas" / "executive-trajectory.schema.json").read_text(encoding="utf-8"))
            jsonschema.validate(ws.executive_status(tr["id"]), schema)
        finally:
            ws.close()
            td.cleanup()

    def test_resource_accounting_machine_truth_is_documented_without_overclaim(self):
        root = Path(__file__).parents[1]
        schema = json.loads((root / "schemas" / "executive-trajectory.schema.json").read_text(encoding="utf-8"))
        budget_state = schema["properties"]["budget_state"]
        properties = budget_state.get("properties") or {}
        self.assertTrue({"consumed", "accounting", "unmetered"}.issubset(properties))

        consumed = ((properties.get("consumed") or {}).get("properties") or {})
        self.assertTrue(
            {"wall_time_ms", "tool_calls", "input_tokens", "output_tokens", "compute_ms"}.issubset(consumed)
        )
        accounting = ((properties.get("accounting") or {}).get("properties") or {})
        self.assertTrue(
            {
                "wall_time",
                "provider_usage",
                "provider_usage_required",
                "receipt_count",
                "invalid_receipt_count",
                "duplicate_receipt_count",
            }.issubset(accounting)
        )

        implementation = (root / "docs" / "IMPLEMENTATION-STATUS.md").read_text(encoding="utf-8")
        limitations = (root / "docs" / "LIMITATIONS.md").read_text(encoding="utf-8")
        combined = (implementation + "\n" + limitations).lower()
        self.assertIn("provider-reported", combined)
        self.assertIn("not independently verified", combined)
        self.assertIn("habitat-measured", combined)
        self.assertNotIn("## executive budgets are only partially metered", limitations.lower())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.observatory_projection_costs import measure_observatory_costs
from habitat.workspace import HabitatWorkspace


class ObservatoryCostEvidenceTests(unittest.TestCase):
    def make_workspace(self):
        td = tempfile.TemporaryDirectory()
        base = Path(td.name)
        source = base / "project"
        source.mkdir()
        (source / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
        ws = HabitatWorkspace.create(source, base / "habitat")
        self.addCleanup(td.cleanup)
        self.addCleanup(ws.close)
        return ws

    def test_headless_cost_evidence_is_descriptive_state_neutral_and_nulls_frontend(self):
        ws = self.make_workspace()
        before = "\n".join(ws.store.conn.iterdump())
        report = measure_observatory_costs(ws, include_frontend=False)
        after = "\n".join(ws.store.conn.iterdump())

        self.assertEqual(before, after)
        self.assertEqual(report["workspace_revision"], ws.revision)
        self.assertGreaterEqual(report["headless_projection_wall_ms"], 0)
        self.assertGreater(report["headless_projection_bytes"], 0)
        self.assertFalse(report["frontend_included"])
        self.assertIsNone(report["frontend_start_wall_ms"])
        self.assertIsNone(report["frontend_health_wall_ms"])
        self.assertIn("descriptive", report["claim_boundary"].lower())
        self.assertIn("no reasoning", report["claim_boundary"].lower())

    def test_frontend_cost_evidence_measures_without_mutating_authoritative_state(self):
        ws = self.make_workspace()
        before = "\n".join(ws.store.conn.iterdump())
        report = measure_observatory_costs(ws, include_frontend=True)
        after = "\n".join(ws.store.conn.iterdump())

        self.assertEqual(before, after)
        self.assertTrue(report["frontend_included"])
        self.assertGreaterEqual(report["frontend_start_wall_ms"], 0)
        self.assertGreaterEqual(report["frontend_health_wall_ms"], 0)


if __name__ == "__main__":
    unittest.main()

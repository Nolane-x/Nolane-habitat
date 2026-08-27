from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.foundation_baseline import collect_baseline


class FoundationBaselineTests(unittest.TestCase):
    def test_collects_cold_warm_context_and_storage_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            (root / "app.py").write_text(
                "def add(a, b):\n    return a + b\n", encoding="utf-8"
            )
            report = collect_baseline(root, "understand add")
            self.assertEqual(report["schema"], "foundation-baseline.v1")
            self.assertEqual(report["suite"], "foundation-baseline")
            self.assertGreaterEqual(report["cold_ingest"]["wall_ms"], 0)
            self.assertGreaterEqual(report["warm_reconcile"]["wall_ms"], 0)
            self.assertIn("available_count", report["semantic_fabric"])
            self.assertGreater(report["storage"]["sqlite_bytes"], 0)
            self.assertEqual(report["orientation"]["task"], "understand add")
            self.assertGreaterEqual(report["source"]["files"], 1)
            self.assertGreaterEqual(report["source"]["symbols"], 1)
            self.assertIn("descriptive", report["claim_boundary"].lower())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.foundation_baseline import collect_baseline


class FoundationBaselineTests(unittest.TestCase):
    def test_collects_cold_warm_context_storage_memory_and_environment_metrics(self):
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

            memory = report["process_memory"]
            self.assertEqual(memory["metric"], "peak_rss")
            self.assertEqual(memory["unit"], "bytes")
            self.assertEqual(memory["scope"], "current_process_lifetime")
            self.assertIn(
                memory["method"],
                {"linux_getrusage", "windows_get_process_memory_info"},
            )
            self.assertIs(type(memory["peak_rss_bytes"]), int)
            self.assertGreater(memory["peak_rss_bytes"], 0)

            environment = report["measurement_environment"]
            self.assertEqual(
                environment["schema"],
                "foundation-measurement-environment.v1",
            )
            for key in (
                "platform_system",
                "platform_release",
                "platform_machine",
                "python_implementation",
                "python_version",
            ):
                self.assertIsInstance(environment[key], str)
                self.assertTrue(environment[key].strip(), key)
            logical_cpu_count = environment["logical_cpu_count"]
            self.assertTrue(
                logical_cpu_count is None
                or (type(logical_cpu_count) is int and logical_cpu_count > 0)
            )
            self.assertIn("descriptive", report["claim_boundary"].lower())


if __name__ == "__main__":
    unittest.main()

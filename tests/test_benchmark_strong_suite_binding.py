from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StrongSuiteFixtureBindingTests(unittest.TestCase):
    def test_strong_mode_rejects_fixture_benchmark_class_mismatch_before_execution(self):
        base = Path(__file__).parents[1]
        harness = base / "benchmarks" / "agent_ab_harness.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite.json"
            suite.write_text(
                json.dumps(
                    {
                        "suite_id": "fixture-class-binding-test",
                        "tasks": [
                            {
                                "id": "mislabeled-task",
                                "benchmark_class": "debugging",
                                "fixture_id": "retrieval-orientation-v1",
                                "prompt": "This declaration must not redefine the fixture taxonomy.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            out = root / "report.json"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(harness),
                    "--strong-evidence",
                    "--suite",
                    str(suite),
                    "--baseline-cmd",
                    sys.executable,
                    "--habitat-cmd",
                    sys.executable,
                    "--evaluator-cmd",
                    sys.executable,
                    "--repetitions",
                    "3",
                    "--model-id",
                    "model-x",
                    "--scaffold-id",
                    "scaffold-x",
                    "--evaluator-id",
                    "evaluator-x",
                    "--environment-fingerprint",
                    "env-x",
                    "--out",
                    str(out),
                ],
                text=True,
                capture_output=True,
                timeout=30,
            )

            self.assertNotEqual(0, proc.returncode)
            self.assertIn("fixture benchmark class mismatch", proc.stderr)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
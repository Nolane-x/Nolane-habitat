import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_RUNNER_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_test_matrix.py"
_SPEC = importlib.util.spec_from_file_location("habitat_test_matrix", _RUNNER_PATH)
assert _SPEC and _SPEC.loader
test_matrix = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(test_matrix)
_REAL_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


class TestMatrixTests(unittest.TestCase):
    def test_cleanup_failure_becomes_a_structured_infra_error(self):
        class CleanupFailure:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                self._temporary = _REAL_TEMPORARY_DIRECTORY()
                return self._temporary.name

            def __exit__(self, exc_type, exc, tb):
                self._temporary.cleanup()
                raise PermissionError("simulated retained shard log")

        with patch.object(test_matrix.tempfile, "TemporaryDirectory", CleanupFailure):
            result = test_matrix.run_group(
                Path(__file__).resolve().parents[1],
                "capabilities",
                ["test_capabilities"],
                60,
            )

        self.assertEqual("infra-error", result["status"])
        self.assertIn("PermissionError", result["error"])

    def test_output_parent_is_created_for_a_successful_matrix_report(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "new-artifacts" / "matrix.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(_RUNNER_PATH),
                    "--mode", "shard",
                    "--match", "test_capabilities",
                    "--out", str(output),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(output.is_file())

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from habitat.semantic.admission import SemanticAdmissionRegistry
from tests.scip_fixture import sample_index


class ScipGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.root = self.base / "source"
        self.root.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
        (self.root / "src" / "b.py").write_text("x = 1\n\nvalue = foo()\n", encoding="utf-8")
        payload, self.symbol = sample_index()
        self.template = self.base / "template.scip"
        self.template.write_bytes(payload)
        self.output = self.root / "generated.scip"
        self.registry = SemanticAdmissionRegistry()
        self.revision = ["rev-1"]
        self.fake = Path(__file__).with_name("fake_scip_indexer.py").resolve()

    def tearDown(self):
        self.tempdir.cleanup()

    def _runtime(self):
        from habitat.semantic.scip_runtime import ScipRuntimeManager

        return ScipRuntimeManager(self.root, self.registry, lambda: self.revision[0])

    def _spec(self, *, mode="success", output=None, timeout_s=2.0, stdout_bytes=0, stderr_bytes=0):
        from habitat.semantic.scip_runtime import ScipIndexerSpec

        target = self.output if output is None else Path(output)
        argv = (
            sys.executable,
            str(self.fake),
            "--mode",
            mode,
            "--input",
            str(self.template),
            "--output",
            str(target),
            "--stdout-bytes",
            str(stdout_bytes),
            "--stderr-bytes",
            str(stderr_bytes),
        )
        if mode == "timeout":
            argv += ("--sleep", "1.0")
        return ScipIndexerSpec(
            provider_id="scip.generated",
            argv=argv,
            output_path=target,
            timeout_s=timeout_s,
        )

    def test_successful_generation_activates_valid_output_and_uses_no_shell(self):
        manager = self._runtime()
        spec = self._spec(stdout_bytes=70_000, stderr_bytes=70_000)

        with mock.patch("habitat.semantic.scip_runtime.subprocess.Popen", wraps=subprocess.Popen) as popen:
            result = manager.generate(spec)

        self.assertTrue(self.output.is_file())
        self.assertTrue(result["admitted"])
        self.assertEqual(result["provider_id"], "scip.generated")
        self.assertEqual(result["generation"]["exit_code"], 0)
        self.assertLessEqual(len(result["generation"]["stdout"].encode("utf-8")), 65_536)
        self.assertLessEqual(len(result["generation"]["stderr"].encode("utf-8")), 65_536)
        self.assertEqual(popen.call_args.kwargs["shell"], False)
        self.assertIsInstance(popen.call_args.args[0], list)
        self.assertEqual(manager.definitions("scip.generated", self.symbol)["locations"][0]["path"], "src/a.py")

    def test_nonzero_exit_fails_without_activation(self):
        from habitat.semantic.scip_runtime import ScipGenerationError

        manager = self._runtime()
        with self.assertRaises(ScipGenerationError) as caught:
            manager.generate(self._spec(mode="nonzero"))
        self.assertEqual(caught.exception.status["exit_code"], 7)
        self.assertFalse(self.registry.is_registered("scip.generated"))

    def test_timeout_terminates_process_and_fails_without_activation(self):
        from habitat.semantic.scip_runtime import ScipGenerationError

        manager = self._runtime()
        with self.assertRaises(ScipGenerationError) as caught:
            manager.generate(self._spec(mode="timeout", timeout_s=0.05))
        self.assertTrue(caught.exception.status["timed_out"])
        self.assertFalse(self.registry.is_registered("scip.generated"))

    def test_zero_exit_without_output_is_rejected(self):
        from habitat.semantic.scip_runtime import ScipGenerationError

        manager = self._runtime()
        with self.assertRaises(ScipGenerationError) as caught:
            manager.generate(self._spec(mode="no-output"))
        self.assertIn("output", caught.exception.status["error"])
        self.assertFalse(self.registry.is_registered("scip.generated"))

    def test_output_path_escape_is_rejected_before_process_start(self):
        manager = self._runtime()
        escaped = self.base / "escaped.scip"
        spec = self._spec(output=escaped)
        with mock.patch("habitat.semantic.scip_runtime.subprocess.Popen", wraps=subprocess.Popen) as popen:
            with self.assertRaises(ValueError):
                manager.generate(spec)
        popen.assert_not_called()

    def test_output_must_be_a_scip_artifact(self):
        manager = self._runtime()
        with self.assertRaises(ValueError):
            manager.generate(self._spec(output=self.root / "not-source.py"))


if __name__ == "__main__":
    unittest.main()

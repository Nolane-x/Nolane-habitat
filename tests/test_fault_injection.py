import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.operations.faults import FaultInjector
from habitat.runtime_lifecycle import shutdown_runtime_services
from habitat.storage import Store


class FaultInjectionTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._temporary.name) / "habitat.sqlite3")

    def tearDown(self):
        self.store.close()
        self._temporary.cleanup()

    def test_fault_after_begin_rolls_back_without_leaving_a_transaction_open(self):
        injector = FaultInjector({"storage.atomic.after_begin": 1})

        with self.assertRaisesRegex(RuntimeError, "injected fault: storage.atomic.after_begin"):
            with self.store.atomic(fault_injector=injector):
                self.store.set_meta("fault-probe", "changed")

        self.assertIsNone(self.store.get_meta("fault-probe"))
        self.assertFalse(self.store.conn.in_transaction)
        self.assertEqual({"storage.atomic.after_begin": 1}, injector.counts)

    def test_fault_before_commit_rolls_back_uncommitted_state(self):
        injector = FaultInjector({"storage.atomic.before_commit": 1})

        with self.assertRaisesRegex(RuntimeError, "injected fault: storage.atomic.before_commit"):
            with self.store.atomic(fault_injector=injector):
                self.store.set_meta("fault-probe", "changed")

        self.assertIsNone(self.store.get_meta("fault-probe"))
        self.assertFalse(self.store.conn.in_transaction)

    def test_shutdown_fault_is_observable_and_does_not_skip_later_services(self):
        injector = FaultInjector({"semantic.shutdown.before_close": 1})
        with patch("habitat.semantic.ts_language_service.close_all_typescript_sessions") as close_typescript, patch(
            "habitat.semantic.python_jedi.close_all_jedi_projects"
        ) as close_jedi:
            report = shutdown_runtime_services(fault_injector=injector)

        self.assertFalse(close_typescript.called)
        close_jedi.assert_called_once_with()
        self.assertEqual("typescript-language-services", report["errors"][0]["service"])
        self.assertIn("jedi-project-cache", report["closed"])

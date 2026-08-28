from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.services import IndexService, QueryService, RuntimeService, TransactionService
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class WorkspaceServiceOwnershipTests(unittest.TestCase):
    def make_reopened_workspace(self, temp: WorkspaceTemporaryDirectory) -> HabitatWorkspace:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text("def target():\n    return 1\n", encoding="utf-8")
        habitat_dir = root / "habitat"
        initial = HabitatWorkspace.create(source, habitat_dir)
        initial.close()
        return HabitatWorkspace(habitat_dir)

    def test_services_are_lazy_and_stable_per_workspace(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_reopened_workspace(temp)
            try:
                self.assertIsNone(getattr(ws, "_index_service", None))
                self.assertIsNone(getattr(ws, "_query_service", None))
                self.assertIsNone(getattr(ws, "_transaction_service", None))
                self.assertIsNone(getattr(ws, "_runtime_service", None))

                index = ws._indexing()
                query = ws._queries()
                transaction = ws._transactions()
                runtime = ws._runtime()

                self.assertIsInstance(index, IndexService)
                self.assertIsInstance(query, QueryService)
                self.assertIsInstance(transaction, TransactionService)
                self.assertIsInstance(runtime, RuntimeService)
                self.assertIs(index, ws._indexing())
                self.assertIs(query, ws._queries())
                self.assertIs(transaction, ws._transactions())
                self.assertIs(runtime, ws._runtime())
            finally:
                ws.close()

    def test_service_construction_performs_no_workspace_operation(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_reopened_workspace(temp)
            try:
                with (
                    patch.object(HabitatWorkspace, "refresh", side_effect=AssertionError("hidden refresh")),
                    patch.object(HabitatWorkspace, "reconcile", side_effect=AssertionError("hidden reconcile")),
                    patch.object(
                        HabitatWorkspace,
                        "semantic_disagreements",
                        side_effect=AssertionError("hidden semantic comparison"),
                    ),
                ):
                    ws._indexing()
                    ws._queries()
                    ws._transactions()
                    ws._runtime()

                self.assertIsNone(getattr(ws, "_lsp_runtime_manager", None))
                self.assertIsNone(getattr(ws, "_scip_runtime_manager", None))
                self.assertIsNone(getattr(ws, "_semantic_disagreement_state", None))
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()

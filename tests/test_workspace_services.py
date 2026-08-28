from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from habitat import _workspace_core as _core
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
                runtime = ws._runtime_operations()

                self.assertIsInstance(index, IndexService)
                self.assertIsInstance(query, QueryService)
                self.assertIsInstance(transaction, TransactionService)
                self.assertIsInstance(runtime, RuntimeService)
                self.assertIs(index, ws._indexing())
                self.assertIs(query, ws._queries())
                self.assertIs(transaction, ws._transactions())
                self.assertIs(runtime, ws._runtime_operations())
            finally:
                ws.close()

    def test_runtime_service_does_not_shadow_existing_browser_runtime_accessor(self):
        self.assertNotIn("_runtime", HabitatWorkspace.__dict__)
        self.assertIn("_runtime", HabitatWorkspace.__mro__[1].__dict__)

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
                    ws._runtime_operations()

                self.assertIsNone(getattr(ws, "_lsp_runtime_manager", None))
                self.assertIsNone(getattr(ws, "_scip_runtime_manager", None))
                self.assertIsNone(getattr(ws, "_semantic_disagreement_state", None))
            finally:
                ws.close()


class IndexServiceRoutingTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory) -> HabitatWorkspace:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text("def target():\n    return 1\n", encoding="utf-8")
        return HabitatWorkspace.create(source, root / "habitat")

    def test_public_index_methods_route_once_through_index_service(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            calls: list[tuple] = []
            try:
                def fake_refresh(service, reason="refresh"):
                    calls.append(("refresh", service, reason))
                    return {"sentinel": "refresh"}

                def fake_refresh_paths(service, paths, reason="targeted-refresh"):
                    calls.append(("refresh_paths", service, tuple(paths), reason))
                    return {"sentinel": "refresh_paths"}

                def fake_reconcile(service):
                    calls.append(("reconcile", service))
                    return {"sentinel": "reconcile"}

                with (
                    patch.object(IndexService, "refresh", new=fake_refresh, create=True),
                    patch.object(IndexService, "refresh_paths", new=fake_refresh_paths, create=True),
                    patch.object(IndexService, "reconcile", new=fake_reconcile, create=True),
                ):
                    self.assertEqual(ws.refresh("route-refresh"), {"sentinel": "refresh"})
                    self.assertEqual(
                        ws.refresh_paths(["sample.py"], "route-paths"),
                        {"sentinel": "refresh_paths"},
                    )
                    self.assertEqual(ws.reconcile(), {"sentinel": "reconcile"})

                service = ws._indexing()
                self.assertEqual(
                    calls,
                    [
                        ("refresh", service, "route-refresh"),
                        ("refresh_paths", service, ("sample.py",), "route-paths"),
                        ("reconcile", service),
                    ],
                )
            finally:
                ws.close()

    def test_index_service_calls_core_explicitly_without_public_recursion(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            service = ws._indexing()
            try:
                with patch.object(
                    _core.HabitatWorkspace,
                    "refresh",
                    return_value={"sentinel": "core-refresh"},
                ) as core_refresh:
                    self.assertEqual(
                        service.refresh("direct-core"),
                        {"sentinel": "core-refresh"},
                    )

                core_refresh.assert_called_once_with(ws, "direct-core")
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()

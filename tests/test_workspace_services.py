from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import habitat.services.index as index_service_module
import habitat.services.query as query_service_module
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

    def test_index_service_calls_preserved_core_explicitly_without_public_recursion(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            service = ws._indexing()
            try:
                with patch.object(
                    index_service_module._CoreHabitatWorkspace,
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


class QueryServiceRoutingTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory) -> HabitatWorkspace:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text("def target():\n    return 1\n", encoding="utf-8")
        return HabitatWorkspace.create(source, root / "habitat")

    def test_public_query_methods_route_once_through_query_service(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            calls: list[tuple] = []
            try:
                def fake_query(service, query, limit=20):
                    calls.append(("query", service, query, limit))
                    return [{"sentinel": "query"}]

                def fake_inspect_snapshot(service, object_id, include_source="none"):
                    calls.append(("inspect_snapshot", service, object_id, include_source))
                    return {"sentinel": "inspect_snapshot"}

                def fake_inspect_many(service, object_ids, include_source="none", max_objects=50):
                    calls.append(("inspect_many", service, tuple(object_ids), include_source, max_objects))
                    return {"sentinel": "inspect_many"}

                def fake_references_snapshot(service, object_id, limit=200):
                    calls.append(("references_snapshot", service, object_id, limit))
                    return {"sentinel": "references_snapshot"}

                def fake_read_source(service, path, start_line=1, max_lines=200):
                    calls.append(("read_source", service, path, start_line, max_lines))
                    return {"sentinel": "read_source"}

                with (
                    patch.object(QueryService, "query", new=fake_query, create=True),
                    patch.object(QueryService, "inspect_snapshot", new=fake_inspect_snapshot, create=True),
                    patch.object(QueryService, "inspect_many", new=fake_inspect_many, create=True),
                    patch.object(QueryService, "references_snapshot", new=fake_references_snapshot, create=True),
                    patch.object(QueryService, "read_source", new=fake_read_source, create=True),
                ):
                    self.assertEqual(ws.query("target", 7), [{"sentinel": "query"}])
                    self.assertEqual(
                        ws.inspect_snapshot("symbol:target", "body"),
                        {"sentinel": "inspect_snapshot"},
                    )
                    self.assertEqual(
                        ws.inspect_many(["symbol:target"], "body", 9),
                        {"sentinel": "inspect_many"},
                    )
                    self.assertEqual(
                        ws.references_snapshot("symbol:target", 11),
                        {"sentinel": "references_snapshot"},
                    )
                    self.assertEqual(
                        ws.read_source("sample.py", 2, 13),
                        {"sentinel": "read_source"},
                    )

                service = ws._queries()
                self.assertEqual(
                    calls,
                    [
                        ("query", service, "target", 7),
                        ("inspect_snapshot", service, "symbol:target", "body"),
                        ("inspect_many", service, ("symbol:target",), "body", 9),
                        ("references_snapshot", service, "symbol:target", 11),
                        ("read_source", service, "sample.py", 2, 13),
                    ],
                )
            finally:
                ws.close()

    def test_query_service_calls_preserved_core_methods_without_public_recursion(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            service = ws._queries()
            try:
                core = query_service_module._CoreHabitatWorkspace
                with (
                    patch.object(core, "query", return_value=[{"sentinel": "core-query"}]) as core_query,
                    patch.object(core, "inspect_snapshot", return_value={"sentinel": "core-inspect"}) as core_inspect,
                    patch.object(core, "inspect_many", return_value={"sentinel": "core-many"}) as core_many,
                    patch.object(core, "references_snapshot", return_value={"sentinel": "core-refs"}) as core_refs,
                    patch.object(core, "read_source", return_value={"sentinel": "core-source"}) as core_source,
                ):
                    self.assertEqual(service.query("needle", 3), [{"sentinel": "core-query"}])
                    self.assertEqual(service.inspect_snapshot("obj", "body"), {"sentinel": "core-inspect"})
                    self.assertEqual(service.inspect_many(["obj"], "body", 4), {"sentinel": "core-many"})
                    self.assertEqual(service.references_snapshot("obj", 5), {"sentinel": "core-refs"})
                    self.assertEqual(service.read_source("sample.py", 2, 6), {"sentinel": "core-source"})

                core_query.assert_called_once_with(ws, "needle", 3)
                core_inspect.assert_called_once_with(ws, "obj", "body")
                core_many.assert_called_once_with(ws, ["obj"], "body", 4)
                core_refs.assert_called_once_with(ws, "obj", 5)
                core_source.assert_called_once_with(ws, "sample.py", 2, 6)
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()

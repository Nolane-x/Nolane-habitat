from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import habitat.services.transaction as transaction_service_module
from habitat.services import TransactionService
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class TransactionServiceRoutingTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory) -> HabitatWorkspace:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text("def target():\n    return 1\n", encoding="utf-8")
        return HabitatWorkspace.create(source, root / "habitat")

    def test_public_transaction_methods_route_once_through_transaction_service(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            calls: list[tuple] = []
            try:
                def fake_change_plan(service, operations):
                    calls.append(("change_plan", service, tuple(operations)))
                    return {"sentinel": "change_plan"}

                def fake_stage_change(
                    service,
                    operations,
                    episode_id=None,
                    agent_id=None,
                    lease_ttl_s=120.0,
                    approval_id=None,
                ):
                    calls.append(
                        (
                            "stage_change",
                            service,
                            tuple(operations),
                            episode_id,
                            agent_id,
                            lease_ttl_s,
                            approval_id,
                        )
                    )
                    return {"sentinel": "stage_change"}

                def fake_stage_symbol_change(service, symbol_id, new_source, episode_id=None, agent_id=None):
                    calls.append(("stage_symbol_change", service, symbol_id, new_source, episode_id, agent_id))
                    return {"sentinel": "stage_symbol_change"}

                def fake_stage_symbol_rename(service, symbol_id, new_name, episode_id=None, agent_id=None):
                    calls.append(("stage_symbol_rename", service, symbol_id, new_name, episode_id, agent_id))
                    return {"sentinel": "stage_symbol_rename"}

                def fake_commit_change(service, txid, agent_id=None):
                    calls.append(("commit_change", service, txid, agent_id))
                    return {"sentinel": "commit_change"}

                def fake_rollback_change(service, txid, agent_id=None):
                    calls.append(("rollback_change", service, txid, agent_id))
                    return {"sentinel": "rollback_change"}

                operations = [{"op": "create_file", "path": "new.py", "source": "x = 1\n"}]
                with (
                    patch.object(TransactionService, "change_plan", new=fake_change_plan, create=True),
                    patch.object(TransactionService, "stage_change", new=fake_stage_change, create=True),
                    patch.object(TransactionService, "stage_symbol_change", new=fake_stage_symbol_change, create=True),
                    patch.object(TransactionService, "stage_symbol_rename", new=fake_stage_symbol_rename, create=True),
                    patch.object(TransactionService, "commit_change", new=fake_commit_change, create=True),
                    patch.object(TransactionService, "rollback_change", new=fake_rollback_change, create=True),
                ):
                    self.assertEqual(ws.change_plan(operations), {"sentinel": "change_plan"})
                    self.assertEqual(
                        ws.stage_change(operations, "ep:1", "agent:1", 45.0, "approval:1"),
                        {"sentinel": "stage_change"},
                    )
                    self.assertEqual(
                        ws.stage_symbol_change("sym:1", "def x():\n    return 2\n", "ep:2", "agent:2"),
                        {"sentinel": "stage_symbol_change"},
                    )
                    self.assertEqual(
                        ws.stage_symbol_rename("sym:2", "renamed", "ep:3", "agent:3"),
                        {"sentinel": "stage_symbol_rename"},
                    )
                    self.assertEqual(ws.commit_change("tx:1", "agent:4"), {"sentinel": "commit_change"})
                    self.assertEqual(ws.rollback_change("tx:2", "agent:5"), {"sentinel": "rollback_change"})

                service = ws._transactions()
                self.assertEqual(
                    calls,
                    [
                        ("change_plan", service, tuple(operations)),
                        ("stage_change", service, tuple(operations), "ep:1", "agent:1", 45.0, "approval:1"),
                        (
                            "stage_symbol_change",
                            service,
                            "sym:1",
                            "def x():\n    return 2\n",
                            "ep:2",
                            "agent:2",
                        ),
                        ("stage_symbol_rename", service, "sym:2", "renamed", "ep:3", "agent:3"),
                        ("commit_change", service, "tx:1", "agent:4"),
                        ("rollback_change", service, "tx:2", "agent:5"),
                    ],
                )
            finally:
                ws.close()

    def test_transaction_service_calls_preserved_core_without_public_recursion(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            service = ws._transactions()
            operations = [{"op": "create_file", "path": "new.py", "source": "x = 1\n"}]
            try:
                core = transaction_service_module._CoreHabitatWorkspace
                with (
                    patch.object(core, "change_plan", return_value={"sentinel": "core-plan"}) as core_plan,
                    patch.object(core, "stage_change", return_value={"sentinel": "core-stage"}) as core_stage,
                    patch.object(core, "stage_symbol_change", return_value={"sentinel": "core-symbol"}) as core_symbol,
                    patch.object(core, "stage_symbol_rename", return_value={"sentinel": "core-rename"}) as core_rename,
                    patch.object(core, "commit_change", return_value={"sentinel": "core-commit"}) as core_commit,
                    patch.object(core, "rollback_change", return_value={"sentinel": "core-rollback"}) as core_rollback,
                ):
                    self.assertEqual(service.change_plan(operations), {"sentinel": "core-plan"})
                    self.assertEqual(
                        service.stage_change(operations, "ep", "agent", 60.0, "approval"),
                        {"sentinel": "core-stage"},
                    )
                    self.assertEqual(
                        service.stage_symbol_change("sym", "source", "ep2", "agent2"),
                        {"sentinel": "core-symbol"},
                    )
                    self.assertEqual(
                        service.stage_symbol_rename("sym2", "name", "ep3", "agent3"),
                        {"sentinel": "core-rename"},
                    )
                    self.assertEqual(service.commit_change("tx1", "agent4"), {"sentinel": "core-commit"})
                    self.assertEqual(service.rollback_change("tx2", "agent5"), {"sentinel": "core-rollback"})

                core_plan.assert_called_once_with(ws, operations)
                core_stage.assert_called_once_with(ws, operations, "ep", "agent", 60.0, "approval")
                core_symbol.assert_called_once_with(ws, "sym", "source", "ep2", "agent2")
                core_rename.assert_called_once_with(ws, "sym2", "name", "ep3", "agent3")
                core_commit.assert_called_once_with(ws, "tx1", "agent4")
                core_rollback.assert_called_once_with(ws, "tx2", "agent5")
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()

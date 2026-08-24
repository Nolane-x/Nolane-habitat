import tempfile
import unittest
from pathlib import Path

from habitat.mutation import MutationEngine, TransactionConflict
from habitat.workspace import HabitatWorkspace


class MutationRecoveryTests(unittest.TestCase):
    @staticmethod
    def _mutation_state(workspace, project: Path, workspace_path: Path) -> dict:
        journal_root = workspace_path / "transactions"
        return {
            "revision": workspace.revision,
            "database": "\n".join(workspace.store.conn.iterdump()),
            "approvals": [
                tuple(row)
                for row in workspace.store.conn.execute(
                    "SELECT id, consumed_at FROM approvals ORDER BY id"
                ).fetchall()
            ],
            "leases": [
                tuple(row)
                for row in workspace.store.conn.execute(
                    "SELECT resource_kind, resource_id, agent_id, transaction_id "
                    "FROM resource_leases ORDER BY resource_kind, resource_id"
                ).fetchall()
            ],
            "journals": [
                (path.relative_to(journal_root).as_posix(), path.read_bytes())
                for path in sorted(journal_root.rglob("*"))
                if path.is_file()
            ]
            if journal_root.exists()
            else [],
            "source": [
                (path.relative_to(project).as_posix(), path.read_bytes())
                for path in sorted(project.rglob("*"))
                if path.is_file()
            ],
        }

    def test_canonical_policy_path_blocks_equivalent_git_hook_mutations(self):
        variants = (
            "./.git/hooks/pre-commit",
            ".git//hooks/./pre-commit",
            ".git\\hooks\\pre-commit",
        )
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                workspace.policy_update(
                    {
                        "source": {"edit": ["**"], "deny": [".git/hooks/pre-commit"]},
                        "structural_mutation": {"approval_required": False},
                    }
                )

                for raw_path in variants:
                    with self.subTest(raw_path=raw_path):
                        decision = workspace.policy_evaluate("edit", path=raw_path)["decision"]
                        self.assertFalse(decision["allowed"])
                        with self.assertRaises(PermissionError):
                            transaction = workspace.stage_change(
                                [
                                    {
                                        "op": "create_file",
                                        "path": raw_path,
                                        "content": "#!/usr/bin/env python\n",
                                        "mode": 0o755,
                                    }
                                ]
                            )
                            workspace.commit_change(transaction["id"])

                self.assertFalse((project / ".git" / "hooks" / "pre-commit").exists())
                self.assertEqual(
                    0,
                    workspace.store.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
                )
            finally:
                workspace.close()

    def test_canonical_policy_path_checks_both_move_endpoints(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "blocked.py").write_text("blocked = True\n", encoding="utf-8")
            (project / "safe.py").write_text("safe = True\n", encoding="utf-8")
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                workspace.policy_update(
                    {
                        "source": {
                            "edit": ["**"],
                            "deny": ["blocked.py", "blocked-target.py"],
                        },
                        "structural_mutation": {"approval_required": False},
                    }
                )

                with self.assertRaises(PermissionError):
                    workspace.stage_change(
                        [
                            {
                                "op": "move_file",
                                "from_path": "./blocked.py",
                                "to_path": "out.py",
                            }
                        ]
                    )
                with self.assertRaises(PermissionError):
                    workspace.stage_change(
                        [
                            {
                                "op": "move_file",
                                "from_path": "./safe.py",
                                "to_path": ".\\blocked-target.py",
                            }
                        ]
                    )
            finally:
                workspace.close()

    def test_equivalent_paths_share_one_agent_lease_resource(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "a.py").write_text("value = 1\n", encoding="utf-8")
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                first_agent = workspace.agent_open("first")["id"]
                second_agent = workspace.agent_open("second")["id"]
                transaction = workspace.stage_change(
                    [
                        {
                            "op": "replace_text",
                            "path": ".\\a.py",
                            "old": "value = 1",
                            "new": "value = 2",
                        }
                    ],
                    agent_id=first_agent,
                )
                self.assertEqual("a.py", transaction["operations"][0]["path"])
                self.assertEqual(["a.py"], transaction["lease_resources"])

                with self.assertRaises(TransactionConflict):
                    workspace.stage_change(
                        [
                            {
                                "op": "replace_text",
                                "path": "./a.py",
                                "old": "value = 1",
                                "new": "value = 3",
                            }
                        ],
                        agent_id=second_agent,
                    )
            finally:
                workspace.close()

    def test_malformed_operation_shapes_are_rejected_before_any_mutation_state(self):
        cases = (
            (
                "operation kind container",
                [{"op": ["replace_text"], "path": "a.py"}],
                "operation op must be a string",
            ),
            (
                "replace text digest container",
                [
                    {
                        "op": "replace_text",
                        "path": "a.py",
                        "old": "return 2",
                        "new": "return 3",
                        "expected_digest": ["not-a-digest"],
                    }
                ],
                "expected_digest must be a string",
            ),
            (
                "replace span digest container",
                [
                    {
                        "op": "replace_span",
                        "path": "a.py",
                        "start_line": 2,
                        "end_line": 2,
                        "start_column": 11,
                        "end_column": 12,
                        "expected_text": "2",
                        "new_text": "3",
                        "expected_digest": {"sha256": "not-a-digest"},
                    }
                ],
                "expected_digest must be a string",
            ),
            (
                "symbol source container",
                [{"op": "replace_symbol_source", "symbol_id": "placeholder", "new_source": 7}],
                "replace_symbol_source requires new_source string",
            ),
            (
                "create content scalar",
                [{"op": "create_file", "path": "new.py", "content": 7}],
                "create_file requires UTF-8 string content",
            ),
            (
                "delete digest container",
                [
                    {
                        "op": "delete_file",
                        "path": "a.py",
                        "expected_digest": ["not-a-digest"],
                    }
                ],
                "expected_digest must be a string",
            ),
            (
                "move digest container",
                [
                    {
                        "op": "move_file",
                        "from_path": "a.py",
                        "to_path": "moved.py",
                        "expected_digest": ["not-a-digest"],
                    }
                ],
                "expected_digest must be a string",
            ),
        )
        for label, operations, message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                project = base / "project"
                project.mkdir()
                source = project / "a.py"
                source.write_text("def target():\n    return 1\n", encoding="utf-8")
                workspace_path = base / "workspace"
                workspace = HabitatWorkspace.create(project, workspace_path)
                try:
                    symbol_id = workspace.store.conn.execute(
                        "SELECT id FROM symbols WHERE name='target'"
                    ).fetchone()[0]
                    if operations[0].get("op") == "replace_symbol_source":
                        operations[0]["symbol_id"] = symbol_id
                    workspace.policy_update(
                        {
                            "source": {"approval": ["a.py"]},
                            "structural_mutation": {"approval_required": True},
                        }
                    )
                    approval = workspace.approval_grant("edit", granted_by="reviewer")
                    agent_id = workspace.agent_open("preflight-agent")["id"]
                    source.write_text("def target():\n    return 2\n", encoding="utf-8")
                    before = self._mutation_state(workspace, project, workspace_path)

                    with self.assertRaises(Exception) as caught:
                        workspace.stage_change(
                            operations,
                            approval_id=approval["id"],
                            agent_id=agent_id,
                        )

                    self.assertEqual(before, self._mutation_state(workspace, project, workspace_path))
                    self.assertIsInstance(caught.exception, (TypeError, ValueError))
                    self.assertRegex(str(caught.exception), message)
                finally:
                    workspace.close()

    def test_denied_symbol_mutation_does_not_reconcile_before_policy_admission(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            source = project / "a.py"
            source.write_text("def target():\n    return 1\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            try:
                symbol_id = workspace.store.conn.execute(
                    "SELECT id FROM symbols WHERE name='target'"
                ).fetchone()[0]
                workspace.policy_update(
                    {
                        "source": {"edit": ["**"], "deny": ["a.py"]},
                        "structural_mutation": {"approval_required": False},
                    }
                )
                approval = workspace.approval_grant("edit", granted_by="reviewer")
                agent_id = workspace.agent_open("denied-agent")["id"]
                source.write_text("def target():\n    return 2\n", encoding="utf-8")
                before = self._mutation_state(workspace, project, workspace_path)

                with self.assertRaises(PermissionError):
                    workspace.stage_change(
                        [
                            {
                                "op": "replace_symbol_source",
                                "symbol_id": symbol_id,
                                "new_source": "def target():\n    return 3",
                            }
                        ],
                        approval_id=approval["id"],
                        agent_id=agent_id,
                    )

                self.assertEqual(before, self._mutation_state(workspace, project, workspace_path))
            finally:
                workspace.close()

    def test_unapproved_symbol_mutation_does_not_reconcile_before_source_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            source = project / "a.py"
            source.write_text("def target():\n    return 1\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            try:
                symbol_id = workspace.store.conn.execute(
                    "SELECT id FROM symbols WHERE name='target'"
                ).fetchone()[0]
                workspace.policy_update(
                    {
                        "source": {"edit": ["**"], "approval": ["a.py"], "deny": []},
                        "structural_mutation": {"approval_required": False},
                    }
                )
                agent_id = workspace.agent_open("unapproved-agent")["id"]
                source.write_text("def target():\n    return 2\n", encoding="utf-8")
                before = self._mutation_state(workspace, project, workspace_path)

                with self.assertRaises(PermissionError):
                    workspace.stage_change(
                        [
                            {
                                "op": "replace_symbol_source",
                                "symbol_id": symbol_id,
                                "new_source": "def target():\n    return 3",
                            }
                        ],
                        agent_id=agent_id,
                    )

                self.assertEqual(before, self._mutation_state(workspace, project, workspace_path))
            finally:
                workspace.close()

    def test_rejects_invalid_operations_before_reconciling_or_persisting(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            source = project / "a.py"
            source.write_text("value = 1\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            try:
                # Deliberately make the source manifest stale. An invalid request must
                # still fail before it can reconcile that drift into SQLite state.
                source.write_text("value = 2\n", encoding="utf-8")
                source_before = source.read_bytes()
                revision_before = workspace.revision
                database_before = "\n".join(workspace.store.conn.iterdump())

                with self.assertRaisesRegex(ValueError, "operations must be a non-empty list"):
                    workspace.stage_change([])

                self.assertEqual(source_before, source.read_bytes())
                self.assertEqual(revision_before, workspace.revision)
                self.assertEqual(database_before, "\n".join(workspace.store.conn.iterdump()))
                self.assertFalse((workspace_path / "transactions").exists())
            finally:
                workspace.close()

    def test_rejects_invalid_payload_before_consuming_approval(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "a.py").write_text("value = 1\n", encoding="utf-8")
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                workspace.policy_update({"structural_mutation": {"approval_required": True}})
                approval = workspace.approval_grant("edit", granted_by="reviewer")

                with self.assertRaisesRegex(ValueError, "create_file requires UTF-8 string content"):
                    workspace.stage_change(
                        [{"op": "create_file", "path": "new.py", "content": 7}],
                        approval_id=approval["id"],
                    )

                consumed_at = workspace.store.conn.execute(
                    "SELECT consumed_at FROM approvals WHERE id=?", (approval["id"],)
                ).fetchone()[0]
                self.assertIsNone(consumed_at)
                self.assertFalse((project / "new.py").exists())
            finally:
                workspace.close()

    def test_reopen_rolls_back_an_interrupted_text_replacement_once(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            source = project / "a.py"
            source.write_text("value = 1\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            engine = MutationEngine(workspace)
            transaction = engine.begin(
                [{"op": "replace_text", "path": "a.py", "old": "value = 1", "new": "value = 2"}]
            )
            originals, outputs, _ = engine._prepare(transaction.operations)
            journal = {
                "version": engine.JOURNAL_VERSION,
                "transaction_id": transaction.id,
                "base_revision": transaction.base_revision,
                "state": "applying",
                "backup_meta": engine._backup(transaction, originals),
                "applied": [{"op": "write", "path": "a.py"}],
                "created_at": "fixture",
            }
            engine._write_journal(transaction.id, journal)
            workspace.write_source_bytes("a.py", outputs["a.py"])
            workspace.close()

            reopened = HabitatWorkspace(workspace_path)
            try:
                self.assertEqual("value = 1\n", source.read_text(encoding="utf-8"))
                self.assertIn(
                    {"transaction_id": transaction.id, "action": "rolled-back-incomplete-transaction"},
                    reopened.enter()["startup_transaction_recovery"],
                )
            finally:
                reopened.close()

            reopened_again = HabitatWorkspace(workspace_path)
            try:
                self.assertEqual([], reopened_again.enter()["startup_transaction_recovery"])
            finally:
                reopened_again.close()

    def test_reopen_restores_a_partial_structural_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "keep.py").write_text("keep = True\n", encoding="utf-8")
            (project / "delete.py").write_text("delete = True\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            engine = MutationEngine(workspace)
            transaction = engine.begin(
                [
                    {"op": "create_file", "path": "created.py", "content": "created = True\n"},
                    {"op": "move_file", "from_path": "keep.py", "to_path": "moved.py"},
                    {"op": "delete_file", "path": "delete.py"},
                ]
            )
            originals, outputs, _ = engine._prepare(transaction.operations)
            journal = {
                "version": engine.JOURNAL_VERSION,
                "transaction_id": transaction.id,
                "base_revision": transaction.base_revision,
                "state": "applying",
                "backup_meta": engine._backup(transaction, originals),
                "applied": [
                    {"op": "write", "path": "created.py"},
                    {"op": "move", "from": "keep.py", "to": "moved.py"},
                    {"op": "delete", "path": "delete.py"},
                ],
                "created_at": "fixture",
            }
            engine._write_journal(transaction.id, journal)
            workspace.write_source_bytes("created.py", outputs["created.py"])
            workspace.move_source_file("keep.py", "moved.py")
            workspace.delete_source_file("delete.py")
            workspace.close()

            reopened = HabitatWorkspace(workspace_path)
            try:
                self.assertEqual("keep = True\n", (project / "keep.py").read_text(encoding="utf-8"))
                self.assertEqual("delete = True\n", (project / "delete.py").read_text(encoding="utf-8"))
                self.assertFalse((project / "created.py").exists())
                self.assertFalse((project / "moved.py").exists())
                self.assertIn(
                    {"transaction_id": transaction.id, "action": "rolled-back-incomplete-transaction"},
                    reopened.enter()["startup_transaction_recovery"],
                )
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()

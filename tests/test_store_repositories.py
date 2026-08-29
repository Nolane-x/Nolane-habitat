from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.model import FileRecord, RelationRecord, SymbolRecord
from habitat.storage import Store, _index_terms


_REPOSITORY_ACCESSORS = (
    "_symbols_repository",
    "_relations_repository",
    "_runtime_repository",
    "_evidence_repository",
    "_experimentation_repository",
    "_learning_repository",
)

_DOMAIN_TABLES = (
    "meta",
    "symbols",
    "relations",
    "runtime_events",
    "evidence",
    "hypotheses",
    "experiments",
    "context_feedback",
    "epistemic_items",
    "project_memories",
)


class StoreRepositoryOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def _snapshot(self) -> dict:
        user_version = int(self.store.conn.execute("PRAGMA user_version").fetchone()[0])
        row_counts = {
            table: int(self.store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _DOMAIN_TABLES
        }
        return {
            "user_version": user_version,
            "in_transaction": bool(self.store.conn.in_transaction),
            "total_changes": int(self.store.conn.total_changes),
            "row_counts": row_counts,
        }

    def test_repository_accessors_are_lazy_stable_and_side_effect_free(self) -> None:
        before = self._snapshot()

        for name in _REPOSITORY_ACCESSORS:
            accessor = getattr(self.store, name, None)
            self.assertTrue(callable(accessor), f"Store must expose repository accessor {name}")
            first = accessor()
            second = accessor()
            self.assertIs(first, second, f"{name} must return one stable repository instance")
            self.assertIs(first.owner, self.store, f"{name} repository must retain its owning Store")

        self.assertEqual(self._snapshot(), before)

    def test_repository_instances_are_not_eagerly_created(self) -> None:
        repository_state = {
            key: value
            for key, value in vars(self.store).items()
            if "repository" in key
        }
        self.assertEqual(repository_state, {})

    def test_index_terms_characterization_is_preserved_before_helper_move(self) -> None:
        self.assertEqual(
            _index_terms("fooBar_baz-qux 12 x HTTPRequest_v2-test"),
            ["bar", "baz", "foo", "httprequest", "qux", "test", "v2"],
        )
        self.assertEqual(_index_terms("A 1 _ -"), [])
        self.assertEqual(_index_terms("alpha alpha ALPHA"), ["alpha"])


class RollbackProbe(RuntimeError):
    pass


class SymbolsRepositoryExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)
        self.file_a = FileRecord(
            id="file:a", path="src/a.py", language="python", size=12, digest="a" * 64, mtime_ns=1
        )
        self.file_b = FileRecord(
            id="file:b", path="src/b.py", language="python", size=12, digest="b" * 64, mtime_ns=2
        )
        self.symbol_a = SymbolRecord(
            id="symbol:a", file_id=self.file_a.id, path=self.file_a.path, name="alphaValue",
            qualified_name="pkg.alphaValue", kind="function", language="python", start_line=3, end_line=6,
            signature="def alphaValue():", summary="alpha helper", trust="parser",
        )
        self.symbol_b = SymbolRecord(
            id="symbol:b", file_id=self.file_b.id, path=self.file_b.path, name="BetaThing",
            qualified_name="pkg.BetaThing", kind="class", language="python", start_line=9, end_line=15,
            signature="class BetaThing:", summary="beta helper", trust="compiler",
        )
        self.store.upsert_file(self.file_a)
        self.store.upsert_file(self.file_b)
        self.store.replace_symbols_for_file(self.file_a.id, [self.symbol_a])
        self.store.replace_symbols_for_file(self.file_b.id, [self.symbol_b])
        self.store.commit()

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    @staticmethod
    def _rows(rows) -> list[tuple]:
        return [tuple(row) for row in rows]

    def _symbol_state(self) -> dict:
        return {
            "symbols": self._rows(self.store.conn.execute("SELECT * FROM symbols ORDER BY id").fetchall()),
            "terms": self._rows(self.store.conn.execute("SELECT * FROM symbol_terms ORDER BY term,symbol_id").fetchall()),
            "relations": self._rows(self.store.conn.execute(
                "SELECT * FROM relations ORDER BY source_id,target_id,kind"
            ).fetchall()),
            "search": self._rows(self.store.conn.execute(
                "SELECT object_id,kind,path,title FROM search_docs ORDER BY object_id"
            ).fetchall()),
        }

    def test_store_symbol_methods_route_once_with_exact_arguments(self) -> None:
        repo = self.store._symbols_repository()
        sentinel = object()

        routes = (
            ("replace_for_file", lambda: self.store.replace_symbols_for_file(self.file_a.id, [self.symbol_a]), (self.file_a.id, [self.symbol_a]), None),
            ("matching_terms", lambda: self.store.symbols_matching_terms(["alpha"], 7), (["alpha"], 7), sentinel),
            ("by_id", lambda: self.store.symbol_by_id(self.symbol_a.id), (self.symbol_a.id,), sentinel),
            ("named", lambda: self.store.symbols_named("alpha"), ("alpha",), sentinel),
            ("for_file", lambda: self.store.symbols_for_file(self.file_a.id), (self.file_a.id,), sentinel),
            ("all", lambda: self.store.all_symbols(), (), sentinel),
        )

        for repository_method, invoke, expected_args, return_value in routes:
            with self.subTest(repository_method=repository_method):
                with patch.object(repo, repository_method, create=True, return_value=return_value) as mocked:
                    result = invoke()
                    mocked.assert_called_once_with(*expected_args)
                    if return_value is sentinel:
                        self.assertIs(result, sentinel)

    def test_repository_reads_match_store_row_shape_order_and_bounds(self) -> None:
        repo = self.store._symbols_repository()

        self.assertEqual(tuple(repo.by_id(self.symbol_a.id)), tuple(self.store.symbol_by_id(self.symbol_a.id)))
        self.assertEqual(self._rows(repo.named("thing")), self._rows(self.store.symbols_named("thing")))
        self.assertEqual(self._rows(repo.for_file(self.file_a.id)), self._rows(self.store.symbols_for_file(self.file_a.id)))
        self.assertEqual(self._rows(repo.all()), self._rows(self.store.all_symbols()))
        self.assertEqual(
            [row["id"] for row in repo.matching_terms(["alpha"], limit=1)],
            [row["id"] for row in self.store.symbols_matching_terms(["alpha"], limit=1)],
        )
        self.assertEqual(repo.matching_terms([], limit=5), [])
        self.assertEqual(repo.matching_terms(["alpha"], limit=0), [])

    def test_replace_symbols_remains_non_committing_and_atomic_rollback_restores_side_effects(self) -> None:
        self.store.replace_relations([
            RelationRecord(
                source_id=self.symbol_a.id, target_id=self.symbol_b.id, kind="calls", trust="parser", evidence="fixture"
            )
        ])
        self.store.commit()
        before = self._symbol_state()
        replacement = SymbolRecord(
            id="symbol:a2", file_id=self.file_a.id, path=self.file_a.path, name="replacementAlpha",
            qualified_name="pkg.replacementAlpha", kind="function", language="python", start_line=20, end_line=23,
            signature="def replacementAlpha():", summary="replacement", trust="parser",
        )

        with self.assertRaises(RollbackProbe):
            with self.store.atomic():
                self.store.replace_symbols_for_file(self.file_a.id, [replacement])
                raise RollbackProbe()

        self.assertEqual(self._symbol_state(), before)



class RelationsRepositoryExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)
        self.base_relations = [
            RelationRecord("symbol:a", "symbol:b", "calls", "parser", "call-site"),
            RelationRecord("symbol:c", "symbol:b", "imports", "compiler", "import-site"),
            RelationRecord("symbol:b", "symbol:d", "inherits", "heuristic", None),
        ]
        self.store.replace_relations(self.base_relations)
        self.store.commit()

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    @staticmethod
    def _rows(rows) -> list[tuple]:
        return [tuple(row) for row in rows]

    def _relation_state(self) -> list[tuple]:
        return self._rows(self.store.conn.execute(
            "SELECT * FROM relations ORDER BY source_id,target_id,kind"
        ).fetchall())

    def test_store_relation_methods_route_once_with_exact_arguments(self) -> None:
        repo = self.store._relations_repository()
        sentinel = object()
        replacement = [RelationRecord("symbol:x", "symbol:y", "calls", "parser", "new")]

        routes = (
            ("replace", lambda: self.store.replace_relations(replacement), (replacement,), None),
            ("sync", lambda: self.store.sync_relations(replacement), (replacement,), sentinel),
            ("for_object", lambda: self.store.relations_for("symbol:b"), ("symbol:b",), sentinel),
            ("incoming", lambda: self.store.incoming_relations("symbol:b", "calls"), ("symbol:b", "calls"), sentinel),
        )

        for repository_method, invoke, expected_args, return_value in routes:
            with self.subTest(repository_method=repository_method):
                with patch.object(repo, repository_method, create=True, return_value=return_value) as mocked:
                    result = invoke()
                    mocked.assert_called_once_with(*expected_args)
                    if return_value is sentinel:
                        self.assertIs(result, sentinel)

    def test_repository_relation_reads_match_store_rows_and_filters(self) -> None:
        repo = self.store._relations_repository()
        self.assertEqual(self._rows(repo.for_object("symbol:b")), self._rows(self.store.relations_for("symbol:b")))
        self.assertEqual(
            self._rows(repo.incoming("symbol:b")),
            self._rows(self.store.incoming_relations("symbol:b")),
        )
        self.assertEqual(
            self._rows(repo.incoming("symbol:b", "calls")),
            self._rows(self.store.incoming_relations("symbol:b", "calls")),
        )

    def test_sync_relations_preserves_exact_change_counts(self) -> None:
        repo = self.store._relations_repository()
        incoming = [
            RelationRecord("symbol:a", "symbol:b", "calls", "compiler", "updated"),
            RelationRecord("symbol:c", "symbol:b", "imports", "compiler", "import-site"),
            RelationRecord("symbol:z", "symbol:b", "references", "parser", "new"),
        ]
        result = repo.sync(incoming)
        self.assertEqual(
            result,
            {"inserted": 1, "updated": 1, "deleted": 1, "unchanged": 1, "total": 3},
        )

    def test_relation_replace_and_sync_remain_non_committing_inside_nested_atomic_rollback(self) -> None:
        before = self._relation_state()
        replacement = [RelationRecord("symbol:x", "symbol:y", "calls", "parser", "replace")]
        synced = [
            RelationRecord("symbol:x", "symbol:y", "calls", "compiler", "sync-update"),
            RelationRecord("symbol:y", "symbol:z", "references", "parser", "sync-new"),
        ]

        with self.assertRaises(RollbackProbe):
            with self.store.atomic():
                with self.store.atomic():
                    self.store.replace_relations(replacement)
                    self.store.sync_relations(synced)
                raise RollbackProbe()

        self.assertEqual(self._relation_state(), before)



class RuntimeRepositoryExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)
        self.events = [
            {
                "id": "runtime:1", "trace_id": "trace:a", "span_id": "span:1", "kind": "tool",
                "name": "first", "status": "ok", "agent_id": "agent:a", "revision": "rev:1",
                "started_at": "2026-08-29T01:00:00Z", "duration_ms": 3.5, "attributes": {"z": 1}, "source": "test",
            },
            {
                "id": "runtime:2", "trace_id": "trace:a", "span_id": "span:2", "kind": "tool",
                "name": "second", "status": "ok", "agent_id": "agent:b", "revision": "rev:1",
                "started_at": "2026-08-29T02:00:00Z", "duration_ms": 4.5, "attributes": {"a": 2}, "source": "test",
            },
            {
                "id": "runtime:3", "trace_id": "trace:b", "span_id": "span:3", "kind": "runtime",
                "name": "third", "status": "observed", "agent_id": "agent:a", "revision": "rev:2",
                "started_at": "2026-08-29T03:00:00Z", "attributes": {},
            },
        ]
        for event in self.events:
            self.store.append_runtime_event(event)

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    @staticmethod
    def _rows(rows) -> list[tuple]:
        return [tuple(row) for row in rows]

    def test_store_runtime_methods_route_once_with_exact_arguments(self) -> None:
        repo = self.store._runtime_repository()
        sentinel = object()
        new_event = {"id": "runtime:new", "revision": "rev:3", "started_at": "2026-08-29T04:00:00Z"}

        with patch.object(repo, "append", create=True, return_value=None) as mocked:
            self.store.append_runtime_event(new_event)
            mocked.assert_called_once_with(new_event)
        with patch.object(repo, "by_id", create=True, return_value=sentinel) as mocked:
            self.assertIs(self.store.runtime_event("runtime:1"), sentinel)
            mocked.assert_called_once_with("runtime:1")
        with patch.object(repo, "list", create=True, return_value=sentinel) as mocked:
            self.assertIs(
                self.store.runtime_events(trace_id="trace:a", agent_id="agent:a", limit=7),
                sentinel,
            )
            mocked.assert_called_once_with(trace_id="trace:a", agent_id="agent:a", limit=7)

    def test_repository_runtime_reads_match_store_filtering_and_order(self) -> None:
        repo = self.store._runtime_repository()
        self.assertEqual(tuple(repo.by_id("runtime:2")), tuple(self.store.runtime_event("runtime:2")))
        self.assertEqual(
            self._rows(repo.list(trace_id="trace:a", limit=10)),
            self._rows(self.store.runtime_events(trace_id="trace:a", limit=10)),
        )
        self.assertEqual(
            self._rows(repo.list(agent_id="agent:a", limit=10)),
            self._rows(self.store.runtime_events(agent_id="agent:a", limit=10)),
        )
        self.assertEqual(
            [row["id"] for row in repo.list(limit=2)],
            ["runtime:3", "runtime:2"],
        )

    def test_runtime_append_preserves_commit_visibility_outside_atomic(self) -> None:
        event = {
            "id": "runtime:committed", "trace_id": "trace:c", "agent_id": "agent:c",
            "revision": "rev:3", "started_at": "2026-08-29T05:00:00Z",
        }
        self.store.append_runtime_event(event)
        second = sqlite3.connect(str(self.db_path))
        try:
            row = second.execute("SELECT id FROM runtime_events WHERE id=?", (event["id"],)).fetchone()
        finally:
            second.close()
        self.assertEqual(row, (event["id"],))

    def test_runtime_append_commit_is_suppressed_by_store_atomic_rollback(self) -> None:
        event = {
            "id": "runtime:rolled-back", "trace_id": "trace:r", "agent_id": "agent:r",
            "revision": "rev:r", "started_at": "2026-08-29T06:00:00Z",
        }
        with self.assertRaises(RollbackProbe):
            with self.store.atomic():
                self.store.append_runtime_event(event)
                raise RollbackProbe()
        self.assertIsNone(self.store.runtime_event(event["id"]))



class EvidenceRepositoryExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)
        self.values = [
            {
                "id": "evidence:1", "kind": "diagnostic", "revision": "rev:1", "path": "src/a.py",
                "object_id": "symbol:a", "severity": "warning", "summary": "first evidence",
                "trust": "parser", "source": "compiler", "data": {"b": 2},
                "created_at": "2026-08-29T01:00:00Z", "active": True,
            },
            {
                "id": "evidence:2", "kind": "test", "revision": "rev:1", "path": "src/b.py",
                "object_id": "symbol:b", "severity": "info", "summary": "second evidence",
                "source": "workspace", "data": {}, "created_at": "2026-08-29T02:00:00Z", "active": True,
            },
            {
                "id": "evidence:3", "kind": "diagnostic", "revision": "rev:2", "path": "src/c.py",
                "object_id": "symbol:c", "summary": "inactive evidence", "source": "compiler",
                "created_at": "2026-08-29T03:00:00Z", "active": False,
            },
        ]
        for value in self.values:
            self.store.append_evidence(value)
        self.store.commit()

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    @staticmethod
    def _rows(rows) -> list[tuple]:
        return [tuple(row) for row in rows]

    def _evidence_state(self) -> dict:
        return {
            "evidence": self._rows(self.store.conn.execute("SELECT * FROM evidence ORDER BY id").fetchall()),
            "search": self._rows(self.store.conn.execute(
                "SELECT object_id,kind,path,title FROM search_docs ORDER BY object_id"
            ).fetchall()),
        }

    def test_store_evidence_methods_route_once_with_exact_arguments(self) -> None:
        repo = self.store._evidence_repository()
        sentinel = object()
        value = {
            "id": "evidence:new", "kind": "test", "revision": "rev:new",
            "summary": "new evidence", "created_at": "2026-08-29T04:00:00Z",
        }
        selectors = {
            "kind": "diagnostic", "paths": ["src/a.py"], "object_ids": ["symbol:a"], "source": "compiler"
        }

        with patch.object(repo, "append", create=True, return_value=None) as mocked:
            self.store.append_evidence(value)
            mocked.assert_called_once_with(value)
        with patch.object(repo, "by_id", create=True, return_value=sentinel) as mocked:
            self.assertIs(self.store.evidence_by_id("evidence:1"), sentinel)
            mocked.assert_called_once_with("evidence:1")
        with patch.object(repo, "active", create=True, return_value=sentinel) as mocked:
            self.assertIs(self.store.active_evidence("diagnostic", 7), sentinel)
            mocked.assert_called_once_with("diagnostic", 7)
        with patch.object(repo, "active_ids", create=True, return_value=sentinel) as mocked:
            self.assertIs(self.store.active_evidence_ids(**selectors), sentinel)
            mocked.assert_called_once_with(**selectors)
        with patch.object(repo, "resolve", create=True, return_value=3) as mocked:
            self.assertEqual(self.store.resolve_evidence(**selectors), 3)
            mocked.assert_called_once_with(**selectors)
        with patch.object(repo, "by_ids", create=True, return_value=sentinel) as mocked:
            ids = ["evidence:2", "evidence:1"]
            self.assertIs(self.store.evidence_by_ids(ids), sentinel)
            mocked.assert_called_once_with(ids)

    def test_repository_evidence_reads_preserve_filters_order_and_defaults(self) -> None:
        repo = self.store._evidence_repository()
        self.assertEqual(tuple(repo.by_id("evidence:1")), tuple(self.store.evidence_by_id("evidence:1")))
        self.assertEqual(
            self._rows(repo.active("diagnostic", 10)),
            self._rows(self.store.active_evidence("diagnostic", 10)),
        )
        self.assertEqual([row["id"] for row in repo.active(None, 10)], ["evidence:2", "evidence:1"])
        kwargs = {"kind": "diagnostic", "paths": ["src/a.py"], "object_ids": ["symbol:x"], "source": "compiler"}
        self.assertEqual(repo.active_ids(**kwargs), self.store.active_evidence_ids(**kwargs))
        row = repo.by_id("evidence:1")
        self.assertEqual(row["data_json"], '{"b":2}')
        self.assertEqual(repo.by_ids([]), [])
        self.assertEqual(
            sorted(row["id"] for row in repo.by_ids(["evidence:2", "evidence:1"])),
            sorted(row["id"] for row in self.store.evidence_by_ids(["evidence:2", "evidence:1"])),
        )

    def test_evidence_append_and_resolve_remain_non_committing_under_atomic_rollback(self) -> None:
        before = self._evidence_state()
        new_value = {
            "id": "evidence:rollback", "kind": "diagnostic", "revision": "rev:r", "path": "src/a.py",
            "object_id": "symbol:a", "summary": "rollback evidence", "source": "compiler",
            "created_at": "2026-08-29T05:00:00Z",
        }
        with self.assertRaises(RollbackProbe):
            with self.store.atomic():
                self.store.append_evidence(new_value)
                resolved = self.store.resolve_evidence(kind="diagnostic", paths=["src/a.py"], source="compiler")
                self.assertGreaterEqual(resolved, 1)
                raise RollbackProbe()
        self.assertEqual(self._evidence_state(), before)



class ExperimentationRepositoryExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)
        self.hypothesis_value = {
            "id": "hypothesis:1", "task": "explain", "statement": "alpha is causal",
            "base_revision": "rev:1", "created_at": "2026-08-29T01:00:00Z",
        }
        self.store.create_hypothesis(self.hypothesis_value)
        self.store.create_episode({
            "id": "episode:x", "task": "experiment fixture", "base_revision": "rev:1",
            "backend_binding": "test", "compiler_fingerprint": "fixture", "created_at": "2026-08-29T01:15:00Z",
        })
        self.store.create_hypothesis({
            "id": "hypothesis:2", "episode_id": "episode:x", "task": "explain", "statement": "beta is causal",
            "status": "rejected", "prior_confidence": "0.7", "current_confidence": "0.25",
            "base_revision": "rev:1", "created_at": "2026-08-29T01:30:00Z", "updated_at": "2026-08-29T03:00:00Z",
        })
        self.experiment_value = {
            "id": "experiment:1", "hypothesis_id": "hypothesis:1", "description": "probe alpha",
            "discriminator": "result differs", "capability": "python",
            "expected": {"z": 1, "a": [2, 1]}, "result": {"before": True},
            "base_revision": "rev:1", "created_at": "2026-08-29T02:00:00Z",
        }
        self.store.create_experiment(self.experiment_value)

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    @staticmethod
    def _rows(rows) -> list[tuple]:
        return [tuple(row) for row in rows]

    def test_store_experimentation_methods_route_once_with_exact_arguments(self) -> None:
        repo = self.store._experimentation_repository()
        sentinel = object()
        value = {"id": "hypothesis:new", "task": "t", "statement": "s", "base_revision": "r", "created_at": "c"}
        experiment = {"id": "experiment:new", "description": "d", "base_revision": "r", "created_at": "c"}

        routes = (
            ("create_hypothesis", lambda: self.store.create_hypothesis(value), (value,), {}, None),
            ("hypothesis", lambda: self.store.hypothesis("hypothesis:1"), ("hypothesis:1",), {}, sentinel),
            ("hypotheses", lambda: self.store.hypotheses("episode:x", "rejected", 7), ("episode:x", "rejected", 7), {}, sentinel),
            ("update_hypothesis", lambda: self.store.update_hypothesis("hypothesis:1", status="accepted", confidence=0.9, updated_at="u"), ("hypothesis:1",), {"status": "accepted", "confidence": 0.9, "updated_at": "u"}, None),
            ("link_hypothesis_evidence", lambda: self.store.link_hypothesis_evidence("hypothesis:1", "evidence:1", "supports", 0.75, "note", "rev:2", "c"), ("hypothesis:1", "evidence:1", "supports", 0.75, "note", "rev:2", "c"), {}, 17),
            ("hypothesis_evidence", lambda: self.store.hypothesis_evidence("hypothesis:1"), ("hypothesis:1",), {}, sentinel),
            ("hypothesis_evidence", lambda: self.store.hypothesis_evidence_rows("hypothesis:1"), ("hypothesis:1",), {}, sentinel),
            ("create_experiment", lambda: self.store.create_experiment(experiment), (experiment,), {}, None),
            ("experiment", lambda: self.store.experiment("experiment:1"), ("experiment:1",), {}, sentinel),
            ("experiments_for_hypothesis", lambda: self.store.experiments_for_hypothesis("hypothesis:1", 7), ("hypothesis:1", 7), {}, sentinel),
            ("complete_experiment", lambda: self.store.complete_experiment("experiment:1", "passed", {"ok": True}, "done"), ("experiment:1", "passed", {"ok": True}, "done"), {}, None),
        )

        for repository_method, invoke, args, kwargs, return_value in routes:
            with self.subTest(repository_method=repository_method, invoke=invoke):
                with patch.object(repo, repository_method, create=True, return_value=return_value) as mocked:
                    result = invoke()
                    mocked.assert_called_once_with(*args, **kwargs)
                    if return_value is sentinel or isinstance(return_value, int):
                        self.assertIs(result, return_value) if return_value is sentinel else self.assertEqual(result, return_value)

    def test_experimentation_defaults_filters_serialization_and_exceptions(self) -> None:
        repo = self.store._experimentation_repository()
        row = repo.hypothesis("hypothesis:1")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["prior_confidence"], 0.5)
        self.assertEqual(row["current_confidence"], 0.5)
        self.assertEqual(
            [r["id"] for r in repo.hypotheses(status="rejected", limit=10)],
            [r["id"] for r in self.store.hypotheses(status="rejected", limit=10)],
        )
        with self.assertRaises(KeyError):
            repo.update_hypothesis("missing", updated_at="u")
        with self.assertRaises(KeyError):
            repo.link_hypothesis_evidence("missing", None, "supports", "0.5", None, "rev", "c")
        experiment = repo.experiment("experiment:1")
        self.assertEqual(json.loads(experiment["expected_json"]), self.experiment_value["expected"])
        self.assertEqual(json.loads(experiment["result_json"]), self.experiment_value["result"])
        with self.assertRaises(KeyError):
            repo.complete_experiment("missing", "failed", {}, "done")

    def test_hypothesis_evidence_weight_and_alias_rows_are_preserved(self) -> None:
        repo = self.store._experimentation_repository()
        seq = repo.link_hypothesis_evidence(
            "hypothesis:1", "evidence:1", "supports", "0.625", "weighted", "rev:2", "2026-08-29T04:00:00Z"
        )
        self.assertGreater(seq, 0)
        rows = repo.hypothesis_evidence("hypothesis:1")
        self.assertEqual(float(rows[-1]["weight"]), 0.625)
        self.assertEqual(self._rows(rows), self._rows(self.store.hypothesis_evidence_rows("hypothesis:1")))

    def test_experimentation_commits_outside_atomic_and_rolls_back_inside_atomic(self) -> None:
        committed = {
            "id": "hypothesis:committed", "task": "t", "statement": "committed",
            "base_revision": "rev:c", "created_at": "2026-08-29T05:00:00Z",
        }
        self.store.create_hypothesis(committed)
        second = sqlite3.connect(str(self.db_path))
        try:
            visible = second.execute("SELECT id FROM hypotheses WHERE id=?", (committed["id"],)).fetchone()
        finally:
            second.close()
        self.assertEqual(visible, (committed["id"],))

        rolled_back = {
            "id": "experiment:rollback", "hypothesis_id": "hypothesis:1", "description": "rollback",
            "expected": {"ok": True}, "base_revision": "rev:r", "created_at": "2026-08-29T06:00:00Z",
        }
        with self.assertRaises(RollbackProbe):
            with self.store.atomic():
                self.store.create_experiment(rolled_back)
                raise RollbackProbe()
        self.assertIsNone(self.store.experiment(rolled_back["id"]))


class LearningRepositoryExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)
        self.store.record_context_feedback(
            "handle:1", "symbol:a", "used", 1.0, ["beta", "alpha", "alpha"], "rev:1", "2026-08-29T01:00:00Z"
        )
        self.store.record_context_feedback(
            "handle:1", "symbol:a", "unhelpful", 0.5, ["alpha"], "rev:2", "2026-08-29T02:00:00Z"
        )
        self.epistemic_value = {
            "id": "epistemic:1", "kind": "claim", "statement": "alpha", "status": "open",
            "confidence": 0.6, "base_revision": "rev:1", "provenance": {"z": 1, "a": [2]},
            "invalidation_conditions": ["source changes"], "created_at": "2026-08-29T01:00:00Z",
            "updated_at": "2026-08-29T01:00:00Z",
        }
        self.store.create_epistemic_item(self.epistemic_value)
        self.store.create_epistemic_item({
            "id": "epistemic:agent", "kind": "claim", "statement": "agent alpha", "status": "open",
            "agent_id": "agent:1", "confidence": 0.4, "base_revision": "rev:1", "created_at": "2026-08-29T02:00:00Z",
            "updated_at": "2026-08-29T03:00:00Z",
        })
        self.memory_value = {
            "id": "memory:global", "kind": "fact", "statement": "xin chào", "base_revision": "rev:1",
            "confidence": 0.8, "provenance": {"source": "test"}, "evidence_ids": ["evidence:2", "evidence:1"],
            "created_at": "2026-08-29T01:00:00Z", "updated_at": "2026-08-29T01:00:00Z",
        }
        self.store.create_project_memory(self.memory_value)
        self.store.create_project_memory({
            "id": "memory:agent", "kind": "fact", "statement": "agent fact", "agent_id": "agent:1",
            "base_revision": "rev:1", "confidence": 0.5, "created_at": "2026-08-29T02:00:00Z",
            "updated_at": "2026-08-29T03:00:00Z",
        })
        self.store.create_project_memory({
            "id": "memory:inactive", "kind": "fact", "statement": "old", "status": "invalidated",
            "base_revision": "rev:1", "created_at": "2026-08-29T02:30:00Z", "updated_at": "2026-08-29T04:00:00Z",
        })

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    @staticmethod
    def _rows(rows) -> list[tuple]:
        return [tuple(row) for row in rows]

    def test_store_learning_methods_route_once_with_exact_arguments(self) -> None:
        repo = self.store._learning_repository()
        sentinel = object()
        epistemic = {
            "id": "epistemic:new", "kind": "claim", "statement": "s", "status": "open",
            "base_revision": "r", "created_at": "c", "updated_at": "u",
        }
        memory = {
            "id": "memory:new", "kind": "fact", "statement": "s", "base_revision": "r",
            "created_at": "c", "updated_at": "u",
        }
        routes = (
            ("record_context_feedback", lambda: self.store.record_context_feedback("h", "o", "used", 0.75, ["b", "a"], "r", "c"),
             ("h", "o", "used", 0.75, ["b", "a"], "r", "c"), {}, 17),
            ("context_utility_for", lambda: self.store.context_utility_for("o", ["a", "b"]), ("o", ["a", "b"]), {}, sentinel),
            ("context_feedback_for_handle", lambda: self.store.context_feedback_for_handle("h", 7), ("h", 7), {}, sentinel),
            ("create_epistemic_item", lambda: self.store.create_epistemic_item(epistemic), (epistemic,), {}, None),
            ("epistemic_item", lambda: self.store.epistemic_item("epistemic:1"), ("epistemic:1",), {}, sentinel),
            ("epistemic_items", lambda: self.store.epistemic_items(kind="claim", status="open", agent_id="agent:1", limit=7), (),
             {"kind": "claim", "status": "open", "agent_id": "agent:1", "limit": 7}, sentinel),
            ("update_epistemic_item", lambda: self.store.update_epistemic_item("epistemic:1", status="verified", confidence=0.9, updated_at="u", provenance={"x": 1}),
             ("epistemic:1",), {"status": "verified", "confidence": 0.9, "updated_at": "u", "provenance": {"x": 1}}, None),
            ("create_project_memory", lambda: self.store.create_project_memory(memory), (memory,), {}, None),
            ("project_memory", lambda: self.store.project_memory("memory:global"), ("memory:global",), {}, sentinel),
            ("find_active_memory", lambda: self.store.find_active_memory("fact", "xin chào", None, "rev:1"),
             ("fact", "xin chào", None, "rev:1"), {}, sentinel),
            ("project_memories", lambda: self.store.project_memories(kind="fact", status=None, agent_id="agent:1", limit=7), (),
             {"kind": "fact", "status": None, "agent_id": "agent:1", "limit": 7}, sentinel),
            ("update_project_memory", lambda: self.store.update_project_memory("memory:global", status="invalidated", confidence=0.2, invalidated_by="rev:2", updated_at="u"),
             ("memory:global",), {"status": "invalidated", "confidence": 0.2, "invalidated_by": "rev:2", "updated_at": "u"}, None),
        )
        for repository_method, invoke, args, kwargs, return_value in routes:
            with self.subTest(repository_method=repository_method):
                with patch.object(repo, repository_method, create=True, return_value=return_value) as mocked:
                    result = invoke()
                    mocked.assert_called_once_with(*args, **kwargs)
                    if return_value is sentinel:
                        self.assertIs(result, sentinel)
                    elif isinstance(return_value, int):
                        self.assertEqual(result, return_value)

    def test_context_feedback_validation_weighting_serialization_and_reads_are_preserved(self) -> None:
        repo = self.store._learning_repository()
        with self.assertRaises(ValueError):
            repo.record_context_feedback("h", "o", "ignored", 1.0, ["x"], "r", "c")
        rows = repo.context_feedback_for_handle("handle:1", 10)
        self.assertEqual(self._rows(rows), self._rows(self.store.context_feedback_for_handle("handle:1", 10)))
        self.assertEqual(json.loads(rows[0]["task_terms_json"]), ["alpha", "beta"])
        utility = repo.context_utility_for("symbol:a", ["beta", "", "alpha", "alpha"])
        self.assertAlmostEqual(utility["useful_weight"], 1.92)
        self.assertAlmostEqual(utility["unhelpful_weight"], 0.5)
        self.assertEqual(set(utility["matched_terms"]), {"alpha", "beta"})
        self.assertEqual(repo.context_utility_for("symbol:a", []), {
            "useful_weight": 0.0, "unhelpful_weight": 0.0, "matched_terms": []
        })

    def test_epistemic_defaults_filters_serialization_and_update_exceptions_are_preserved(self) -> None:
        repo = self.store._learning_repository()
        row = repo.epistemic_item("epistemic:1")
        self.assertEqual(row["scope"], "workspace")
        self.assertEqual(json.loads(row["provenance_json"]), self.epistemic_value["provenance"])
        self.assertEqual(json.loads(row["invalidation_json"]), self.epistemic_value["invalidation_conditions"])
        self.assertEqual(
            self._rows(repo.epistemic_items(kind="claim", status="open", agent_id="agent:1", limit=10)),
            self._rows(self.store.epistemic_items(kind="claim", status="open", agent_id="agent:1", limit=10)),
        )
        self.assertEqual(
            {r["id"] for r in repo.epistemic_items(kind="claim", status="open", agent_id="agent:1", limit=10)},
            {"epistemic:1", "epistemic:agent"},
        )
        with self.assertRaises(KeyError):
            repo.update_epistemic_item("missing", updated_at="u")
        repo.update_epistemic_item("epistemic:1", confidence=0.75, updated_at="u", provenance={"β": "ok"})
        updated = repo.epistemic_item("epistemic:1")
        self.assertEqual(updated["status"], "open")
        self.assertEqual(updated["confidence"], 0.75)
        self.assertEqual(json.loads(updated["provenance_json"]), {"β": "ok"})

    def test_project_memory_defaults_scope_filters_unicode_and_update_exceptions_are_preserved(self) -> None:
        repo = self.store._learning_repository()
        row = repo.project_memory("memory:global")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["scope"], "workspace")
        self.assertEqual(json.loads(row["provenance_json"]), self.memory_value["provenance"])
        self.assertEqual(json.loads(row["evidence_json"]), self.memory_value["evidence_ids"])
        self.assertEqual(repo.find_active_memory("fact", "xin chào", None, "rev:1")["id"], "memory:global")
        self.assertEqual(repo.find_active_memory("fact", "agent fact", "agent:1", "rev:1")["id"], "memory:agent")
        self.assertIsNone(repo.find_active_memory("fact", "agent fact", None, "rev:1"))
        self.assertEqual(
            {r["id"] for r in repo.project_memories(kind="fact", agent_id="agent:1", limit=10)},
            {"memory:global", "memory:agent"},
        )
        self.assertEqual(
            self._rows(repo.project_memories(kind="fact", status=None, agent_id="agent:1", limit=10)),
            self._rows(self.store.project_memories(kind="fact", status=None, agent_id="agent:1", limit=10)),
        )
        with self.assertRaises(KeyError):
            repo.update_project_memory("missing", updated_at="u")
        repo.update_project_memory("memory:global", confidence=0.95, updated_at="u")
        updated = repo.project_memory("memory:global")
        self.assertEqual(updated["status"], "active")
        self.assertEqual(updated["confidence"], 0.95)
        self.assertIsNone(updated["invalidated_by"])

    def test_learning_writes_commit_outside_atomic_and_are_suppressed_inside_atomic(self) -> None:
        committed = {
            "id": "memory:committed", "kind": "fact", "statement": "visible", "base_revision": "rev:c",
            "created_at": "2026-08-29T05:00:00Z", "updated_at": "2026-08-29T05:00:00Z",
        }
        self.store.create_project_memory(committed)
        second = sqlite3.connect(str(self.db_path))
        try:
            visible = second.execute("SELECT id FROM project_memories WHERE id=?", (committed["id"],)).fetchone()
        finally:
            second.close()
        self.assertEqual(visible, (committed["id"],))

        before_feedback = [tuple(r) for r in self.store.context_feedback_for_handle("handle:rollback", 10)]
        with self.assertRaises(RollbackProbe):
            with self.store.atomic():
                self.store.record_context_feedback(
                    "handle:rollback", "symbol:r", "used", 1.0, ["rollback"], "rev:r", "2026-08-29T06:00:00Z"
                )
                self.store.create_epistemic_item({
                    "id": "epistemic:rollback", "kind": "claim", "statement": "rollback", "status": "open",
                    "base_revision": "rev:r", "created_at": "2026-08-29T06:00:00Z", "updated_at": "2026-08-29T06:00:00Z",
                })
                raise RollbackProbe()
        self.assertEqual([tuple(r) for r in self.store.context_feedback_for_handle("handle:rollback", 10)], before_feedback)
        self.assertEqual(self.store.context_utility_for("symbol:r", ["rollback"])["useful_weight"], 0.0)
        self.assertIsNone(self.store.epistemic_item("epistemic:rollback"))


if __name__ == "__main__":
    unittest.main()

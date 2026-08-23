from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from .database_health import inspect_connection
from .model import DiagnosticRecord, EventRecord, FileRecord, OccurrenceRecord, RelationRecord, Revision, SymbolRecord
from .storage_migrations import (
    SCHEMA_VERSION,
    additive_schema_issues,
    create_pre_migration_backup,
    migration_backup_version,
    preflight_schema_version,
    repair_additive_columns,
    verify_required_structure,
)

_JSON_TABLES = {"transactions", "runs", "context_slices", "sessions"}


class StoreBusyError(RuntimeError):
    """Raised when a separate SQLite writer exceeds Habitat's contention budget."""


class _TransactionAwareConnection(sqlite3.Connection):
    """Prevent legacy helper commits from escaping an explicit Store transaction."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._habitat_transaction_depth = 0

    def commit(self) -> None:
        if self._habitat_transaction_depth == 0:
            super().commit()

    def commit_atomic(self) -> None:
        super().commit()


def _index_terms(value: str) -> list[str]:
    value=re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",value or "").replace("_"," ").replace("-"," ")
    return sorted({x.casefold() for x in re.findall(r"\w+",value,flags=re.UNICODE) if len(x)>=2 and not x.isdigit()})

class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), factory=_TransactionAwareConnection)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self._init_schema()

    @contextmanager
    def atomic(self):
        """Commit all workspace updates together, or roll them all back on failure."""

        nested = self.conn.in_transaction or self.conn._habitat_transaction_depth > 0
        savepoint = f"habitat_atomic_{self.conn._habitat_transaction_depth}"
        try:
            if nested:
                self.conn.execute(f"SAVEPOINT {savepoint}")
            else:
                self.conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if "busy" in str(exc).lower() or "locked" in str(exc).lower():
                raise StoreBusyError(
                    "Habitat workspace database is busy; retry after the active writer completes."
                ) from exc
            raise
        self.conn._habitat_transaction_depth += 1
        try:
            yield
        except BaseException:
            if nested:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                self.conn.rollback()
            raise
        else:
            if nested:
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                self.conn.commit_atomic()
        finally:
            self.conn._habitat_transaction_depth -= 1

    def _init_schema(self) -> None:
        preflight_schema_version(self.conn)
        backup_version = migration_backup_version(self.conn)
        if backup_version is not None:
            create_pre_migration_backup(self.conn, self.db_path, backup_version)
        c = self.conn.cursor()
        c.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS files(
              id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, language TEXT NOT NULL,
              size INTEGER NOT NULL, digest TEXT NOT NULL, mtime_ns INTEGER NOT NULL,
              indexed_bytes INTEGER NOT NULL DEFAULT 0, index_truncated INTEGER NOT NULL DEFAULT 0,
              parse_complete INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS symbols(
              id TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
              path TEXT NOT NULL, name TEXT NOT NULL, qualified_name TEXT NOT NULL,
              kind TEXT NOT NULL, language TEXT NOT NULL, start_line INTEGER NOT NULL,
              end_line INTEGER NOT NULL, signature TEXT, summary TEXT, trust TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_symbols_qname ON symbols(qualified_name);
            CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(path);
            CREATE TABLE IF NOT EXISTS symbol_terms(
              term TEXT NOT NULL, symbol_id TEXT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE, path TEXT NOT NULL,
              PRIMARY KEY(term,symbol_id)
            );
            CREATE INDEX IF NOT EXISTS idx_symbol_terms_term ON symbol_terms(term,symbol_id);
            CREATE INDEX IF NOT EXISTS idx_symbol_terms_path ON symbol_terms(path,term);
            CREATE TABLE IF NOT EXISTS relations(
              source_id TEXT NOT NULL, target_id TEXT NOT NULL, kind TEXT NOT NULL,
              trust TEXT NOT NULL, evidence TEXT,
              PRIMARY KEY(source_id, target_id, kind)
            );
            CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id);
            CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id);
            CREATE INDEX IF NOT EXISTS idx_rel_kind ON relations(kind);
            CREATE TABLE IF NOT EXISTS diagnostics(
              id TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
              path TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL,
              line INTEGER, column INTEGER, source TEXT NOT NULL, trust TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_diag_path ON diagnostics(path);
            CREATE INDEX IF NOT EXISTS idx_diag_severity ON diagnostics(severity);
            CREATE TABLE IF NOT EXISTS occurrences(
              id TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
              path TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT, source_id TEXT, text TEXT NOT NULL,
              start_line INTEGER NOT NULL, start_column INTEGER, end_line INTEGER, end_column INTEGER,
              provider TEXT NOT NULL, trust TEXT NOT NULL, evidence TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_occ_target ON occurrences(target_id);
            CREATE INDEX IF NOT EXISTS idx_occ_source ON occurrences(source_id);
            CREATE INDEX IF NOT EXISTS idx_occ_path ON occurrences(path);
            CREATE INDEX IF NOT EXISTS idx_occ_role ON occurrences(role);
            CREATE TABLE IF NOT EXISTS events(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, path TEXT, observed_at TEXT NOT NULL,
              revision_before TEXT, revision_after TEXT, old_digest TEXT, new_digest TEXT,
              source TEXT NOT NULL, details_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
            CREATE INDEX IF NOT EXISTS idx_events_path ON events(path);
            CREATE TABLE IF NOT EXISTS activity_events(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, category TEXT NOT NULL,
              agent_id TEXT, episode_id TEXT, ref_id TEXT, path TEXT, revision TEXT NOT NULL,
              status TEXT NOT NULL, summary TEXT NOT NULL, data_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_activity_events_kind ON activity_events(kind,seq);
            CREATE INDEX IF NOT EXISTS idx_activity_events_agent ON activity_events(agent_id,seq);
            CREATE INDEX IF NOT EXISTS idx_activity_events_episode ON activity_events(episode_id,seq);
            CREATE INDEX IF NOT EXISTS idx_activity_events_path ON activity_events(path,seq);
            CREATE TABLE IF NOT EXISTS epistemic_items(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, statement TEXT NOT NULL, status TEXT NOT NULL,
              confidence REAL, scope TEXT NOT NULL DEFAULT 'workspace', agent_id TEXT, episode_id TEXT,
              base_revision TEXT NOT NULL, provenance_json TEXT NOT NULL DEFAULT '{}', invalidation_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_epistemic_items_kind ON epistemic_items(kind,status,updated_at);
            CREATE INDEX IF NOT EXISTS idx_epistemic_items_agent ON epistemic_items(agent_id,status,updated_at);
            CREATE TABLE IF NOT EXISTS project_memories(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, statement TEXT NOT NULL, status TEXT NOT NULL, scope TEXT NOT NULL,
              agent_id TEXT, episode_id TEXT, base_revision TEXT NOT NULL, confidence REAL, provenance_json TEXT NOT NULL DEFAULT '{}',
              evidence_json TEXT NOT NULL DEFAULT '[]', valid_until_revision TEXT, supersedes TEXT, invalidated_by TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_project_memories_kind ON project_memories(kind,status,updated_at);
            CREATE INDEX IF NOT EXISTS idx_project_memories_agent ON project_memories(agent_id,status,updated_at);
            CREATE TABLE IF NOT EXISTS runtime_events(
              id TEXT PRIMARY KEY, trace_id TEXT, span_id TEXT, parent_span_id TEXT, kind TEXT NOT NULL, name TEXT NOT NULL,
              status TEXT NOT NULL, path TEXT, symbol_id TEXT, agent_id TEXT, episode_id TEXT, revision TEXT NOT NULL,
              started_at TEXT NOT NULL, duration_ms REAL, attributes_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runtime_events_trace ON runtime_events(trace_id,started_at);
            CREATE INDEX IF NOT EXISTS idx_runtime_events_path ON runtime_events(path,started_at);
            CREATE INDEX IF NOT EXISTS idx_runtime_events_agent ON runtime_events(agent_id,started_at);
            CREATE TABLE IF NOT EXISTS effect_facts(
              id TEXT PRIMARY KEY, path TEXT NOT NULL, symbol_id TEXT, kind TEXT NOT NULL, target TEXT NOT NULL,
              line INTEGER, trust TEXT NOT NULL, evidence TEXT, revision TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_effect_facts_path ON effect_facts(path,kind,line);
            CREATE INDEX IF NOT EXISTS idx_effect_facts_symbol ON effect_facts(symbol_id,kind);
            CREATE INDEX IF NOT EXISTS idx_effect_facts_target ON effect_facts(target,kind);
            CREATE TABLE IF NOT EXISTS dataflow_facts(
              id TEXT PRIMARY KEY, path TEXT NOT NULL, symbol_id TEXT, kind TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL,
              line INTEGER, trust TEXT NOT NULL, evidence TEXT, revision TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dataflow_facts_path ON dataflow_facts(path,kind,line);
            CREATE INDEX IF NOT EXISTS idx_dataflow_facts_symbol ON dataflow_facts(symbol_id,kind);
            CREATE INDEX IF NOT EXISTS idx_dataflow_facts_source ON dataflow_facts(source,kind);
            CREATE INDEX IF NOT EXISTS idx_dataflow_facts_target ON dataflow_facts(target,kind);
            CREATE TABLE IF NOT EXISTS counterfactual_worlds(
              id TEXT PRIMARY KEY, label TEXT NOT NULL, owner_agent_id TEXT, base_revision TEXT NOT NULL, status TEXT NOT NULL,
              overlay_root TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_counterfactual_worlds_owner ON counterfactual_worlds(owner_agent_id,status,updated_at);
            CREATE TABLE IF NOT EXISTS counterfactual_changes(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT NOT NULL REFERENCES counterfactual_worlds(id) ON DELETE CASCADE,
              path TEXT NOT NULL, op TEXT NOT NULL, base_digest TEXT, overlay_digest TEXT, byte_size INTEGER NOT NULL DEFAULT 0,
              metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, UNIQUE(world_id,path)
            );
            CREATE INDEX IF NOT EXISTS idx_counterfactual_changes_world ON counterfactual_changes(world_id,seq);
            CREATE TABLE IF NOT EXISTS project_cache(key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS merkle_objects(
              hash TEXT PRIMARY KEY, kind TEXT NOT NULL, value_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS merkle_snapshots(
              revision_id TEXT PRIMARY KEY, root_hash TEXT NOT NULL, file_count INTEGER NOT NULL, byte_size INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_merkle_snapshots_root ON merkle_snapshots(root_hash);
            CREATE TABLE IF NOT EXISTS evidence(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, revision TEXT NOT NULL, path TEXT, object_id TEXT, severity TEXT NOT NULL,
              summary TEXT NOT NULL, trust TEXT NOT NULL, source TEXT NOT NULL, data_json TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_active ON evidence(active,kind);
            CREATE INDEX IF NOT EXISTS idx_evidence_path ON evidence(path,active);
            CREATE INDEX IF NOT EXISTS idx_evidence_object ON evidence(object_id,active);
            CREATE TABLE IF NOT EXISTS resident_objects(
              object_id TEXT PRIMARY KEY, kind TEXT NOT NULL, path TEXT NOT NULL, admitted_revision TEXT NOT NULL,
              source_digest TEXT, relevance REAL NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0,
              source_bytes_estimate INTEGER NOT NULL DEFAULT 0, access_count INTEGER NOT NULL DEFAULT 0, last_access_seq INTEGER NOT NULL DEFAULT 0,
              admitted_at TEXT NOT NULL, last_touched_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_resident_access ON resident_objects(pinned,last_access_seq,relevance);
            CREATE TABLE IF NOT EXISTS trace_sessions(
              id TEXT PRIMARY KEY, label TEXT NOT NULL, started_at TEXT NOT NULL, stopped_at TEXT,
              start_revision TEXT NOT NULL, end_revision TEXT, active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS trace_calls(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT NOT NULL REFERENCES trace_sessions(id) ON DELETE CASCADE,
              method TEXT NOT NULL, ok INTEGER NOT NULL, duration_ms INTEGER NOT NULL, request_bytes INTEGER NOT NULL,
              response_bytes INTEGER NOT NULL, source_bytes INTEGER NOT NULL DEFAULT 0, revision TEXT NOT NULL, recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trace_calls_trace ON trace_calls(trace_id,seq);
            CREATE TABLE IF NOT EXISTS context_feedback(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, object_id TEXT NOT NULL, verdict TEXT NOT NULL,
              weight REAL NOT NULL, task_terms_json TEXT NOT NULL, revision TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_context_feedback_handle ON context_feedback(handle,seq);
            CREATE INDEX IF NOT EXISTS idx_context_feedback_object ON context_feedback(object_id,seq);
            CREATE TABLE IF NOT EXISTS context_utility(
              object_id TEXT NOT NULL, term TEXT NOT NULL, useful_weight REAL NOT NULL DEFAULT 0,
              unhelpful_weight REAL NOT NULL DEFAULT 0, last_revision TEXT NOT NULL, updated_at TEXT NOT NULL,
              PRIMARY KEY(object_id,term)
            );
            CREATE INDEX IF NOT EXISTS idx_context_utility_term ON context_utility(term,object_id);
            CREATE TABLE IF NOT EXISTS work_episodes(
              id TEXT PRIMARY KEY, task TEXT NOT NULL, context_handle TEXT, base_revision TEXT NOT NULL,
              backend_binding TEXT NOT NULL, compiler_fingerprint TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, closed_at TEXT, outcome_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_work_episodes_status ON work_episodes(status,created_at);
            CREATE TABLE IF NOT EXISTS episode_links(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, episode_id TEXT NOT NULL REFERENCES work_episodes(id) ON DELETE CASCADE,
              kind TEXT NOT NULL, ref_id TEXT, revision TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_episode_links_episode ON episode_links(episode_id,seq);
            CREATE INDEX IF NOT EXISTS idx_episode_links_ref ON episode_links(ref_id,seq);
            CREATE TABLE IF NOT EXISTS context_faults(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, page_id TEXT NOT NULL, object_id TEXT NOT NULL,
              path TEXT NOT NULL, source_bytes INTEGER NOT NULL, authority_bytes_read INTEGER NOT NULL DEFAULT 0, revision TEXT NOT NULL, episode_id TEXT, fetched_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_context_faults_handle ON context_faults(handle,seq);
            CREATE INDEX IF NOT EXISTS idx_context_faults_episode ON context_faults(episode_id,seq);
            CREATE INDEX IF NOT EXISTS idx_context_faults_object ON context_faults(object_id,seq);
            CREATE TABLE IF NOT EXISTS causal_edges(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, source_kind TEXT NOT NULL, source_ref TEXT NOT NULL, relation TEXT NOT NULL,
              target_kind TEXT NOT NULL, target_ref TEXT NOT NULL, revision TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_causal_source ON causal_edges(source_ref,seq);
            CREATE INDEX IF NOT EXISTS idx_causal_target ON causal_edges(target_ref,seq);
            CREATE INDEX IF NOT EXISTS idx_causal_revision ON causal_edges(revision,seq);
            CREATE TABLE IF NOT EXISTS hypotheses(
              id TEXT PRIMARY KEY, episode_id TEXT, task TEXT NOT NULL, statement TEXT NOT NULL,
              status TEXT NOT NULL, prior_confidence REAL NOT NULL, current_confidence REAL NOT NULL,
              base_revision TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY(episode_id) REFERENCES work_episodes(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hypotheses_episode ON hypotheses(episode_id,status,updated_at);
            CREATE TABLE IF NOT EXISTS hypothesis_evidence(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
              evidence_id TEXT, polarity TEXT NOT NULL, weight REAL NOT NULL, note TEXT, revision TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_h ON hypothesis_evidence(hypothesis_id,seq);
            CREATE TABLE IF NOT EXISTS experiments(
              id TEXT PRIMARY KEY, hypothesis_id TEXT REFERENCES hypotheses(id) ON DELETE SET NULL, episode_id TEXT,
              description TEXT NOT NULL, discriminator TEXT, status TEXT NOT NULL, capability TEXT,
              expected_json TEXT NOT NULL DEFAULT '{}', result_json TEXT NOT NULL DEFAULT '{}',
              base_revision TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT,
              FOREIGN KEY(episode_id) REFERENCES work_episodes(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_experiments_hypothesis ON experiments(hypothesis_id,status,created_at);
            CREATE TABLE IF NOT EXISTS agent_sessions(
              id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_agent_sessions_status ON agent_sessions(status,updated_at);
            CREATE TABLE IF NOT EXISTS agent_context_utility(
              agent_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE, object_id TEXT NOT NULL, term TEXT NOT NULL,
              useful_weight REAL NOT NULL DEFAULT 0, unhelpful_weight REAL NOT NULL DEFAULT 0, last_revision TEXT NOT NULL, updated_at TEXT NOT NULL,
              PRIMARY KEY(agent_id,object_id,term)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_utility_term ON agent_context_utility(agent_id,term,object_id);
            CREATE TABLE IF NOT EXISTS resource_leases(
              resource_kind TEXT NOT NULL, resource_id TEXT NOT NULL, agent_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
              transaction_id TEXT, revision TEXT NOT NULL, acquired_at TEXT NOT NULL, expires_at REAL NOT NULL,
              PRIMARY KEY(resource_kind,resource_id)
            );
            CREATE INDEX IF NOT EXISTS idx_resource_leases_agent ON resource_leases(agent_id,expires_at);
            CREATE TABLE IF NOT EXISTS agent_observations(
              agent_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE, path TEXT NOT NULL, object_id TEXT NOT NULL DEFAULT '',
              digest TEXT, revision TEXT NOT NULL, kind TEXT NOT NULL, observed_at TEXT NOT NULL,
              PRIMARY KEY(agent_id,path,object_id)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_observations_path ON agent_observations(path,agent_id);
            CREATE TABLE IF NOT EXISTS agent_notifications(
              id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE, kind TEXT NOT NULL,
              resource_kind TEXT NOT NULL, resource_id TEXT NOT NULL, revision TEXT NOT NULL, caused_by_transaction TEXT,
              data_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, acked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_agent_notifications_agent ON agent_notifications(agent_id,status,created_at);
            CREATE TABLE IF NOT EXISTS agent_resident_objects(
              agent_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE, object_id TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL,
              admitted_revision TEXT NOT NULL, source_digest TEXT, relevance REAL NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0,
              access_count INTEGER NOT NULL DEFAULT 0, last_access_seq INTEGER NOT NULL DEFAULT 0, admitted_at TEXT NOT NULL, last_touched_at TEXT NOT NULL,
              PRIMARY KEY(agent_id,object_id)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_residency_access ON agent_resident_objects(agent_id,pinned,last_access_seq,relevance);
            CREATE TABLE IF NOT EXISTS agent_hypothesis_beliefs(
              agent_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
              hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
              stance TEXT NOT NULL, confidence REAL NOT NULL, rationale TEXT, base_revision TEXT NOT NULL, updated_at TEXT NOT NULL,
              PRIMARY KEY(agent_id,hypothesis_id)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_hypothesis_beliefs_agent ON agent_hypothesis_beliefs(agent_id,stance,updated_at);
            CREATE TABLE IF NOT EXISTS approvals(
              id TEXT PRIMARY KEY, action TEXT NOT NULL, resource TEXT, agent_id TEXT, granted_by TEXT NOT NULL,
              status TEXT NOT NULL, expires_at REAL NOT NULL, created_at TEXT NOT NULL, consumed_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_approvals_lookup ON approvals(status,action,resource,agent_id,expires_at);
            CREATE TABLE IF NOT EXISTS project_invariants(
              id TEXT PRIMARY KEY, statement TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL,
              base_revision TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_project_invariants_status ON project_invariants(status,severity,updated_at);
            CREATE TABLE IF NOT EXISTS invariant_links(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, invariant_id TEXT NOT NULL REFERENCES project_invariants(id) ON DELETE CASCADE,
              ref_kind TEXT NOT NULL, ref_id TEXT NOT NULL, relation TEXT NOT NULL, revision TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_invariant_links_inv ON invariant_links(invariant_id,seq);
            CREATE INDEX IF NOT EXISTS idx_invariant_links_ref ON invariant_links(ref_id,seq);
            CREATE TABLE IF NOT EXISTS executive_trajectories(
              id TEXT PRIMARY KEY, goal TEXT NOT NULL, agent_id TEXT, episode_id TEXT, status TEXT NOT NULL,
              base_revision TEXT NOT NULL, current_strategy TEXT NOT NULL, strategy_generation INTEGER NOT NULL DEFAULT 0,
              budget_json TEXT NOT NULL DEFAULT '{}', metrics_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_at TEXT, outcome_json TEXT NOT NULL DEFAULT '{}',
              FOREIGN KEY(agent_id) REFERENCES agent_sessions(id) ON DELETE SET NULL,
              FOREIGN KEY(episode_id) REFERENCES work_episodes(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_executive_trajectories_status ON executive_trajectories(status,updated_at);
            CREATE INDEX IF NOT EXISTS idx_executive_trajectories_agent ON executive_trajectories(agent_id,status,updated_at);
            CREATE TABLE IF NOT EXISTS executive_milestones(
              id TEXT PRIMARY KEY, trajectory_id TEXT NOT NULL REFERENCES executive_trajectories(id) ON DELETE CASCADE,
              title TEXT NOT NULL, postcondition TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL,
              dependencies_json TEXT NOT NULL DEFAULT '[]', verifier_ref TEXT, rollback TEXT, base_revision TEXT NOT NULL,
              result_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_executive_milestones_trajectory ON executive_milestones(trajectory_id,status,priority,created_at);
            CREATE TABLE IF NOT EXISTS executive_events(
              row_id INTEGER PRIMARY KEY AUTOINCREMENT, trajectory_id TEXT NOT NULL REFERENCES executive_trajectories(id) ON DELETE CASCADE,
              ordinal INTEGER NOT NULL, phase TEXT NOT NULL, operation TEXT NOT NULL, status TEXT NOT NULL, revision TEXT NOT NULL,
              ref_id TEXT, data_json TEXT NOT NULL DEFAULT '{}', previous_hash TEXT, record_hash TEXT NOT NULL, created_at TEXT NOT NULL,
              UNIQUE(trajectory_id,ordinal)
            );
            CREATE INDEX IF NOT EXISTS idx_executive_events_trajectory ON executive_events(trajectory_id,ordinal);
            CREATE INDEX IF NOT EXISTS idx_executive_events_ref ON executive_events(ref_id,trajectory_id);
            CREATE TABLE IF NOT EXISTS revisions(
              id TEXT PRIMARY KEY, parent_id TEXT, root_digest TEXT NOT NULL, reason TEXT NOT NULL,
              changed_paths TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS context_slices(id TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS compile_cache(file_id TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS search_docs(
              rowid INTEGER PRIMARY KEY AUTOINCREMENT,
              object_id TEXT UNIQUE NOT NULL,
              kind TEXT NOT NULL,
              path TEXT NOT NULL,
              title TEXT NOT NULL
            );
            """
        )
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(path,title,body,content='',contentless_delete=1)")
            self._set_meta_uncommitted("fts5", "contentless")
        except sqlite3.OperationalError:
            try:
                c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(path,title,body)")
                self._set_meta_uncommitted("fts5", "regular")
            except sqlite3.OperationalError:
                self._set_meta_uncommitted("fts5", "0")
        repair_additive_columns(self.conn)
        verify_required_structure(self.conn)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._set_meta_uncommitted("schema_version", str(SCHEMA_VERSION))
        self.conn.commit()
        self._ensure_symbol_terms_index()

    def _ensure_symbol_terms_index(self) -> None:
        version="symbol-terms-v1"
        if self.get_meta("symbol_terms_index_version") == version:
            return
        self.conn.execute("DELETE FROM symbol_terms")
        for row in self.conn.execute("SELECT id,path,qualified_name FROM symbols").fetchall():
            for term in _index_terms((row["qualified_name"] or "")+" "+(row["path"] or "")):
                self.conn.execute("INSERT OR IGNORE INTO symbol_terms(term,symbol_id,path) VALUES(?,?,?)",(term,row["id"],row["path"]))
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('symbol_terms_index_version',?)",(version,))
        self.conn.commit()

    # --- alpha.12 effect twin / counterfactual worlds ---
    def replace_effect_facts_for_path(self, path: str, facts: list[dict]) -> int:
        self.conn.execute("DELETE FROM effect_facts WHERE path=?", (path,))
        for value in facts:
            self.conn.execute(
                """INSERT INTO effect_facts(id,path,symbol_id,kind,target,line,trust,evidence,revision,metadata_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (value["id"], value["path"], value.get("symbol_id"), value["kind"], value.get("target", ""),
                 value.get("line"), value.get("trust", "parser"), value.get("evidence"), value["revision"],
                 json.dumps(value.get("metadata") or {}, sort_keys=True), value["created_at"]),
            )
        self.conn.commit(); return len(facts)

    def effect_facts(self, *, path: str | None = None, symbol_id: str | None = None, kind: str | None = None, limit: int = 1000):
        clauses=[]; args=[]
        if path is not None: clauses.append("path=?"); args.append(path)
        if symbol_id is not None: clauses.append("symbol_id=?"); args.append(symbol_id)
        if kind is not None: clauses.append("kind=?"); args.append(kind)
        sql="SELECT * FROM effect_facts"+(" WHERE "+" AND ".join(clauses) if clauses else "")+" ORDER BY path,line,id LIMIT ?"
        args.append(int(limit)); return self.conn.execute(sql, tuple(args)).fetchall()

    def delete_effect_facts_for_path(self, path: str) -> None:
        self.conn.execute("DELETE FROM effect_facts WHERE path=?", (path,)); self.conn.commit()

    def replace_dataflow_facts_for_path(self, path: str, facts: list[dict]) -> int:
        self.conn.execute("DELETE FROM dataflow_facts WHERE path=?", (path,))
        for value in facts:
            self.conn.execute(
                """INSERT INTO dataflow_facts(id,path,symbol_id,kind,source,target,line,trust,evidence,revision,metadata_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (value["id"], value["path"], value.get("symbol_id"), value["kind"], value.get("source", ""), value.get("target", ""),
                 value.get("line"), value.get("trust", "parser"), value.get("evidence"), value["revision"],
                 json.dumps(value.get("metadata") or {}, sort_keys=True), value["created_at"]),
            )
        self.conn.commit(); return len(facts)

    def dataflow_facts(self, *, path: str | None = None, symbol_id: str | None = None, kind: str | None = None, source: str | None = None, target: str | None = None, limit: int = 1000):
        clauses=[]; args=[]
        for col,val in (("path",path),("symbol_id",symbol_id),("kind",kind),("source",source),("target",target)):
            if val is not None: clauses.append(f"{col}=?"); args.append(val)
        sql="SELECT * FROM dataflow_facts"+(" WHERE "+" AND ".join(clauses) if clauses else "")+" ORDER BY path,line,id LIMIT ?"
        args.append(int(limit)); return self.conn.execute(sql, tuple(args)).fetchall()

    def delete_dataflow_facts_for_path(self, path: str) -> None:
        self.conn.execute("DELETE FROM dataflow_facts WHERE path=?", (path,)); self.conn.commit()

    def create_counterfactual_world(self, value: dict) -> None:
        self.conn.execute(
            "INSERT INTO counterfactual_worlds(id,label,owner_agent_id,base_revision,status,overlay_root,created_at,updated_at,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
            (value["id"], value["label"], value.get("owner_agent_id"), value["base_revision"], value.get("status", "open"),
             value["overlay_root"], value["created_at"], value["updated_at"], json.dumps(value.get("metadata") or {}, sort_keys=True)),
        ); self.conn.commit()

    def counterfactual_world(self, world_id: str):
        return self.conn.execute("SELECT * FROM counterfactual_worlds WHERE id=?", (world_id,)).fetchone()

    def counterfactual_worlds(self, owner_agent_id: str | None = None, status: str | None = None, limit: int = 100):
        clauses=[]; args=[]
        if owner_agent_id is not None: clauses.append("owner_agent_id=?"); args.append(owner_agent_id)
        if status is not None: clauses.append("status=?"); args.append(status)
        sql="SELECT * FROM counterfactual_worlds"+(" WHERE "+" AND ".join(clauses) if clauses else "")+" ORDER BY updated_at DESC LIMIT ?"
        args.append(int(limit)); return self.conn.execute(sql, tuple(args)).fetchall()

    def update_counterfactual_world(self, world_id: str, *, status: str | None = None, updated_at: str, metadata: dict | None = None) -> None:
        row=self.counterfactual_world(world_id)
        if not row: raise KeyError(world_id)
        new_status=status or row["status"]
        try: oldmeta=json.loads(row["metadata_json"] or "{}")
        except Exception: oldmeta={}
        if metadata: oldmeta.update(metadata)
        self.conn.execute("UPDATE counterfactual_worlds SET status=?,updated_at=?,metadata_json=? WHERE id=?",
                          (new_status,updated_at,json.dumps(oldmeta,sort_keys=True),world_id)); self.conn.commit()

    def upsert_counterfactual_change(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO counterfactual_changes(world_id,path,op,base_digest,overlay_digest,byte_size,metadata_json,created_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(world_id,path) DO UPDATE SET op=excluded.op,base_digest=excluded.base_digest,overlay_digest=excluded.overlay_digest,
                 byte_size=excluded.byte_size,metadata_json=excluded.metadata_json,created_at=excluded.created_at""",
            (value["world_id"],value["path"],value["op"],value.get("base_digest"),value.get("overlay_digest"),int(value.get("byte_size",0)),
             json.dumps(value.get("metadata") or {},sort_keys=True),value["created_at"]),
        ); self.conn.commit()

    def counterfactual_changes(self, world_id: str):
        return self.conn.execute("SELECT * FROM counterfactual_changes WHERE world_id=? ORDER BY seq", (world_id,)).fetchall()

    def close(self) -> None:
        conn = getattr(self, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self.conn = None

    def doctor(self) -> dict:
        """Return a read-only health report for the Habitat workspace database."""

        return inspect_connection(self.conn)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _set_meta_uncommitted(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))

    def set_meta(self, key: str, value: str) -> None:
        self._set_meta_uncommitted(key, value)
        self.conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def upsert_file(self, f: FileRecord) -> None:
        self.conn.execute(
            """INSERT INTO files(id,path,language,size,digest,mtime_ns,indexed_bytes,index_truncated,parse_complete)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET id=excluded.id,language=excluded.language,size=excluded.size,
                 digest=excluded.digest,mtime_ns=excluded.mtime_ns,indexed_bytes=excluded.indexed_bytes,
                 index_truncated=excluded.index_truncated,parse_complete=excluded.parse_complete""",
            (f.id, f.path, f.language, f.size, f.digest, f.mtime_ns, f.indexed_bytes, int(f.index_truncated), int(f.parse_complete)),
        )

    def replace_symbols_for_file(self, file_id: str, symbols: Iterable[SymbolRecord]) -> None:
        old_ids = [r[0] for r in self.conn.execute("SELECT id FROM symbols WHERE file_id=?", (file_id,))]
        for oid in old_ids:
            self.conn.execute("DELETE FROM relations WHERE source_id=? OR target_id=?", (oid, oid))
            self.delete_search(oid)
        self.conn.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
        for s in symbols:
            self.conn.execute(
                """INSERT INTO symbols(id,file_id,path,name,qualified_name,kind,language,start_line,end_line,signature,summary,trust)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s.id, s.file_id, s.path, s.name, s.qualified_name, s.kind, s.language,
                 s.start_line, s.end_line, s.signature, s.summary, s.trust),
            )
            body = " ".join(filter(None, [s.signature, s.summary]))
            self.index_search(s.id, "symbol", s.path, s.qualified_name, body)
            for term in _index_terms(s.qualified_name + " " + s.path):
                self.conn.execute("INSERT OR IGNORE INTO symbol_terms(term,symbol_id,path) VALUES(?,?,?)",(term,s.id,s.path))

    def symbols_matching_terms(self, terms: list[str], limit: int = 1000):
        """Bounded indexed candidate retrieval; avoids scanning every symbol for every task."""
        if not terms or limit < 1:
            return []
        ids=[]; seen=set()
        for raw in terms[:64]:
            term=str(raw).casefold()
            if not term: continue
            prefixes=[term]
            if len(term)>=7:
                prefixes.append(term[:-1] if term.endswith("s") else term)
                for suffix in ("ation","tion","ment","ing","ed","ity","ness"):
                    if term.endswith(suffix) and len(term)-len(suffix)>=4:
                        prefixes.append(term[:-len(suffix)])
            clauses=[]; args=[]
            for pfx in dict.fromkeys(prefixes):
                clauses.append("term=? OR term LIKE ?"); args.extend([pfx,pfx+"%"] if len(pfx)>=4 else [pfx,pfx])
            sql="SELECT DISTINCT symbol_id FROM symbol_terms WHERE "+" OR ".join(f"({c})" for c in clauses)+" LIMIT ?"
            rows=self.conn.execute(sql,[*args,min(250,int(limit))]).fetchall()
            for r in rows:
                oid=r["symbol_id"]
                if oid not in seen:
                    seen.add(oid); ids.append(oid)
                    if len(ids)>=limit: break
            if len(ids)>=limit: break
        if not ids: return []
        marks=",".join("?" for _ in ids)
        rows=self.conn.execute(f"SELECT * FROM symbols WHERE id IN ({marks})",ids).fetchall()
        by={r["id"]:r for r in rows}
        return [by[i] for i in ids if i in by]

    def replace_diagnostics_for_file(self, file_id: str, diagnostics: Iterable[DiagnosticRecord]) -> None:
        old_ids = [r[0] for r in self.conn.execute("SELECT id FROM diagnostics WHERE file_id=?", (file_id,))]
        for oid in old_ids:
            self.delete_search(oid)
        self.conn.execute("DELETE FROM diagnostics WHERE file_id=?", (file_id,))
        for d in diagnostics:
            self.conn.execute(
                """INSERT INTO diagnostics(id,file_id,path,severity,message,line,column,source,trust)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (d.id, d.file_id, d.path, d.severity, d.message, d.line, d.column, d.source, d.trust),
            )
            self.index_search(d.id, "diagnostic", d.path, f"{d.severity}: {d.message}", d.message)

    def replace_file_search(self, f: FileRecord) -> None:
        self.delete_search(f.id)
        self.index_search(f.id, "file", f.path, f.path, f.indexed_text)

    def delete_search(self, object_id: str) -> None:
        mode = self.get_meta("fts5", "0")
        row = self.conn.execute("SELECT rowid FROM search_docs WHERE object_id=?", (object_id,)).fetchone()
        if row and mode != "0":
            try:
                self.conn.execute("DELETE FROM search_fts WHERE rowid=?", (row["rowid"],))
            except sqlite3.OperationalError:
                # Legacy regular FTS tables may reject a contentless-delete path; rebuildability
                # matters more than preserving a stale index row during schema migration.
                pass
        self.conn.execute("DELETE FROM search_docs WHERE object_id=?", (object_id,))

    def index_search(self, object_id: str, kind: str, path: str, title: str, body: str) -> None:
        mode = self.get_meta("fts5", "0")
        if mode == "0":
            return
        cur = self.conn.execute(
            "INSERT INTO search_docs(object_id,kind,path,title) VALUES(?,?,?,?)",
            (object_id, kind, path, title),
        )
        rowid = cur.lastrowid
        self.conn.execute(
            "INSERT INTO search_fts(rowid,path,title,body) VALUES(?,?,?,?)",
            (rowid, path, title, body[:200_000]),
        )

    def replace_occurrences(self, occurrences: Iterable[OccurrenceRecord]) -> None:
        self.conn.execute("DELETE FROM occurrences")
        for o in occurrences:
            self.conn.execute(
                """INSERT INTO occurrences(id,file_id,path,role,target_id,source_id,text,start_line,start_column,end_line,end_column,provider,trust,evidence)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (o.id, o.file_id, o.path, o.role, o.target_id, o.source_id, o.text, o.start_line,
                 o.start_column, o.end_line, o.end_column, o.provider, o.trust, o.evidence),
            )

    def sync_occurrences(self, occurrences: Iterable[OccurrenceRecord]) -> dict:
        """Synchronize occurrence rows without rewriting an unchanged graph.

        This makes semantic refresh cost observable: callers receive inserted/updated/deleted/unchanged
        counts instead of Habitat silently dropping and recreating the entire relation index.
        """
        incoming = {o.id: o for o in occurrences}
        current = {r["id"]: r for r in self.conn.execute("SELECT * FROM occurrences").fetchall()}
        inserted = updated = unchanged = 0
        fields = ("file_id","path","role","target_id","source_id","text","start_line","start_column","end_line","end_column","provider","trust","evidence")
        for oid, o in incoming.items():
            row = current.get(oid)
            values = (o.file_id,o.path,o.role,o.target_id,o.source_id,o.text,o.start_line,o.start_column,o.end_line,o.end_column,o.provider,o.trust,o.evidence)
            if row is None:
                self.conn.execute(
                    """INSERT INTO occurrences(id,file_id,path,role,target_id,source_id,text,start_line,start_column,end_line,end_column,provider,trust,evidence)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (oid,*values),
                )
                inserted += 1
            elif tuple(row[f] for f in fields) != values:
                self.conn.execute(
                    """UPDATE occurrences SET file_id=?,path=?,role=?,target_id=?,source_id=?,text=?,start_line=?,start_column=?,end_line=?,end_column=?,provider=?,trust=?,evidence=? WHERE id=?""",
                    (*values,oid),
                )
                updated += 1
            else:
                unchanged += 1
        deleted_ids = set(current) - set(incoming)
        if deleted_ids:
            self.conn.executemany("DELETE FROM occurrences WHERE id=?", [(x,) for x in deleted_ids])
        return {"inserted": inserted, "updated": updated, "deleted": len(deleted_ids), "unchanged": unchanged, "total": len(incoming)}

    def occurrences_for_target(self, object_id: str):
        return self.conn.execute("SELECT * FROM occurrences WHERE target_id=? ORDER BY path,start_line,start_column", (object_id,)).fetchall()

    def occurrences_from_source(self, object_id: str):
        return self.conn.execute("SELECT * FROM occurrences WHERE source_id=? ORDER BY path,start_line,start_column", (object_id,)).fetchall()

    def occurrences_for_path(self, path: str):
        return self.conn.execute("SELECT * FROM occurrences WHERE path=? ORDER BY start_line,start_column", (path,)).fetchall()

    def occurrence_by_id(self, object_id: str):
        return self.conn.execute("SELECT * FROM occurrences WHERE id=?", (object_id,)).fetchone()

    def append_evidence(self, value: dict) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO evidence(id,kind,revision,path,object_id,severity,summary,trust,source,data_json,created_at,active)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value["kind"],value["revision"],value.get("path"),value.get("object_id"),value.get("severity","info"),
             value["summary"],value.get("trust","derived"),value.get("source","workspace"),json.dumps(value.get("data",{}),separators=(",",":")),
             value["created_at"],int(value.get("active",True))),
        )
        self.delete_search(value["id"])
        self.index_search(value["id"],"evidence",value.get("path") or "",value["summary"],value["summary"])

    def evidence_by_id(self, evidence_id: str):
        return self.conn.execute("SELECT * FROM evidence WHERE id=?",(evidence_id,)).fetchone()

    def active_evidence(self, kind: str | None = None, limit: int = 500):
        if kind:
            return self.conn.execute("SELECT * FROM evidence WHERE active=1 AND kind=? ORDER BY created_at DESC LIMIT ?",(kind,limit)).fetchall()
        return self.conn.execute("SELECT * FROM evidence WHERE active=1 ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()

    def active_evidence_ids(self, *, kind: str | None = None, paths: list[str] | None = None, object_ids: list[str] | None = None, source: str | None = None) -> list[str]:
        clauses=["active=1"]; args=[]
        if kind: clauses.append("kind=?"); args.append(kind)
        if source: clauses.append("source=?"); args.append(source)
        selectors=[]
        if paths:
            selectors.append("path IN (%s)" % ",".join("?" for _ in paths)); args.extend(paths)
        if object_ids:
            selectors.append("object_id IN (%s)" % ",".join("?" for _ in object_ids)); args.extend(object_ids)
        if selectors: clauses.append("("+" OR ".join(selectors)+")")
        return [r["id"] for r in self.conn.execute("SELECT id FROM evidence WHERE "+" AND ".join(clauses)+" ORDER BY created_at,id",tuple(args)).fetchall()]

    def resolve_evidence(self, *, kind: str | None = None, paths: list[str] | None = None, object_ids: list[str] | None = None, source: str | None = None) -> int:
        clauses=["active=1"]; args=[]
        if kind: clauses.append("kind=?"); args.append(kind)
        if source: clauses.append("source=?"); args.append(source)
        selectors=[]
        if paths:
            selectors.append("path IN (%s)" % ",".join("?" for _ in paths)); args.extend(paths)
        if object_ids:
            selectors.append("object_id IN (%s)" % ",".join("?" for _ in object_ids)); args.extend(object_ids)
        if selectors: clauses.append("("+" OR ".join(selectors)+")")
        cur=self.conn.execute("UPDATE evidence SET active=0 WHERE "+" AND ".join(clauses),tuple(args))
        return int(cur.rowcount or 0)

    def save_merkle_snapshot(self, revision_id: str, snapshot: dict, created_at: str) -> None:
        """Persist a content-addressed Merkle snapshot without duplicating unchanged subtrees."""
        for leaf in snapshot.get("leaves", {}).values():
            value = {"content_digest": leaf["content_digest"], "size": int(leaf["size"])}
            self.conn.execute("INSERT OR IGNORE INTO merkle_objects(hash,kind,value_json) VALUES(?,?,?)",
                              (leaf["hash"], "file", json.dumps(value, separators=(",", ":"))))
        for node in snapshot.get("nodes", {}).values():
            value = {"children": node.get("children", []), "file_count": int(node.get("file_count", 0)),
                     "byte_size": int(node.get("byte_size", 0))}
            self.conn.execute("INSERT OR IGNORE INTO merkle_objects(hash,kind,value_json) VALUES(?,?,?)",
                              (node["hash"], "tree", json.dumps(value, separators=(",", ":"))))
        self.conn.execute("INSERT OR REPLACE INTO merkle_snapshots(revision_id,root_hash,file_count,byte_size,created_at) VALUES(?,?,?,?,?)",
                          (revision_id, snapshot["root_hash"], int(snapshot.get("file_count", 0)), int(snapshot.get("byte_size", 0)), created_at))

    def merkle_snapshot_row(self, revision_id: str):
        return self.conn.execute("SELECT * FROM merkle_snapshots WHERE revision_id=?", (revision_id,)).fetchone()

    def merkle_object(self, object_hash: str) -> dict | None:
        row = self.conn.execute("SELECT kind,value_json FROM merkle_objects WHERE hash=?", (object_hash,)).fetchone()
        if not row: return None
        value = json.loads(row["value_json"]); value["hash"] = object_hash; value["kind"] = row["kind"]
        return value

    def merkle_stats(self) -> dict:
        obj = self.conn.execute("SELECT COUNT(*) AS n FROM merkle_objects").fetchone()["n"]
        snaps = self.conn.execute("SELECT COUNT(*) AS n FROM merkle_snapshots").fetchone()["n"]
        return {"objects": int(obj), "snapshots": int(snaps)}

    def save_project_cache(self, key: str, value: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO project_cache(key,value_json) VALUES(?,?)", (key, json.dumps(value)))

    def load_project_cache(self, key: str) -> dict | None:
        row = self.conn.execute("SELECT value_json FROM project_cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def project_cache_keys(self, prefix: str = "") -> list[str]:
        if prefix:
            rows = self.conn.execute("SELECT key FROM project_cache WHERE key LIKE ? ORDER BY key", (prefix + "%",)).fetchall()
        else:
            rows = self.conn.execute("SELECT key FROM project_cache ORDER BY key").fetchall()
        return [str(r[0]) for r in rows]

    def delete_project_cache(self, key: str) -> None:
        self.conn.execute("DELETE FROM project_cache WHERE key=?", (key,))

    def upsert_resident(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO resident_objects(object_id,kind,path,admitted_revision,source_digest,relevance,pinned,source_bytes_estimate,access_count,last_access_seq,admitted_at,last_touched_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(object_id) DO UPDATE SET kind=excluded.kind,path=excluded.path,admitted_revision=excluded.admitted_revision,
                 source_digest=excluded.source_digest,relevance=MAX(resident_objects.relevance,excluded.relevance),
                 pinned=MAX(resident_objects.pinned,excluded.pinned),source_bytes_estimate=excluded.source_bytes_estimate,access_count=resident_objects.access_count+1,
                 last_access_seq=excluded.last_access_seq,last_touched_at=excluded.last_touched_at""",
            (value["object_id"],value["kind"],value["path"],value["admitted_revision"],value.get("source_digest"),
             float(value.get("relevance",0.0)),int(bool(value.get("pinned"))),int(value.get("source_bytes_estimate",0)),int(value.get("access_count",1)),
             int(value.get("last_access_seq",0)),value["admitted_at"],value["last_touched_at"]),
        )

    def resident_rows(self):
        return self.conn.execute("SELECT * FROM resident_objects ORDER BY pinned DESC,last_access_seq DESC,relevance DESC,object_id").fetchall()

    def resident_by_id(self, object_id: str):
        return self.conn.execute("SELECT * FROM resident_objects WHERE object_id=?", (object_id,)).fetchone()

    def delete_resident(self, object_id: str) -> None:
        self.conn.execute("DELETE FROM resident_objects WHERE object_id=?", (object_id,))

    def clear_residents(self) -> None:
        self.conn.execute("DELETE FROM resident_objects")

    def set_resident_pin(self, object_id: str, pinned: bool) -> None:
        self.conn.execute("UPDATE resident_objects SET pinned=? WHERE object_id=?", (int(bool(pinned)), object_id))

    def touch_resident(self, object_id: str, seq: int, touched_at: str) -> None:
        self.conn.execute("UPDATE resident_objects SET access_count=access_count+1,last_access_seq=?,last_touched_at=? WHERE object_id=?", (seq,touched_at,object_id))

    def create_trace(self, trace_id: str, label: str, started_at: str, revision: str) -> None:
        self.conn.execute(
            "INSERT INTO trace_sessions(id,label,started_at,start_revision,active) VALUES(?,?,?,?,1)",
            (trace_id,label,started_at,revision),
        )
        self.conn.commit()

    def active_trace(self):
        return self.conn.execute("SELECT * FROM trace_sessions WHERE active=1 ORDER BY started_at DESC LIMIT 1").fetchone()

    def trace_by_id(self, trace_id: str):
        return self.conn.execute("SELECT * FROM trace_sessions WHERE id=?", (trace_id,)).fetchone()

    def stop_trace(self, trace_id: str, stopped_at: str, revision: str) -> None:
        self.conn.execute("UPDATE trace_sessions SET stopped_at=?,end_revision=?,active=0 WHERE id=?", (stopped_at,revision,trace_id))
        self.conn.commit()

    def append_trace_call(self, trace_id: str, method: str, ok: bool, duration_ms: int, request_bytes: int, response_bytes: int, source_bytes: int, revision: str, recorded_at: str) -> int:
        cur=self.conn.execute(
            """INSERT INTO trace_calls(trace_id,method,ok,duration_ms,request_bytes,response_bytes,source_bytes,revision,recorded_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (trace_id,method,int(ok),duration_ms,request_bytes,response_bytes,source_bytes,revision,recorded_at),
        )
        self.conn.commit(); return int(cur.lastrowid)

    def trace_calls(self, trace_id: str):
        return self.conn.execute("SELECT * FROM trace_calls WHERE trace_id=? ORDER BY seq", (trace_id,)).fetchall()

    def record_context_feedback(self, handle: str, object_id: str, verdict: str, weight: float, task_terms: list[str], revision: str, created_at: str) -> int:
        if verdict not in {"used", "unhelpful"}:
            raise ValueError("context feedback verdict must be used or unhelpful")
        cur = self.conn.execute(
            "INSERT INTO context_feedback(handle,object_id,verdict,weight,task_terms_json,revision,created_at) VALUES(?,?,?,?,?,?,?)",
            (handle, object_id, verdict, float(weight), json.dumps(sorted(set(task_terms))), revision, created_at),
        )
        useful = float(weight) if verdict == "used" else 0.0
        unhelpful = float(weight) if verdict == "unhelpful" else 0.0
        for term in sorted(set(task_terms)):
            self.conn.execute(
                """INSERT INTO context_utility(object_id,term,useful_weight,unhelpful_weight,last_revision,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(object_id,term) DO UPDATE SET
                     useful_weight=MIN(10.0, context_utility.useful_weight*0.92+excluded.useful_weight),
                     unhelpful_weight=MIN(10.0, context_utility.unhelpful_weight*0.92+excluded.unhelpful_weight),
                     last_revision=excluded.last_revision,updated_at=excluded.updated_at""",
                (object_id, term, useful, unhelpful, revision, created_at),
            )
        self.conn.commit()
        return int(cur.lastrowid)

    def context_utility_for(self, object_id: str, terms: list[str]) -> dict:
        terms = sorted(set(t for t in terms if t))
        if not terms:
            return {"useful_weight": 0.0, "unhelpful_weight": 0.0, "matched_terms": []}
        marks = ",".join("?" for _ in terms)
        rows = self.conn.execute(
            f"SELECT term,useful_weight,unhelpful_weight FROM context_utility WHERE object_id=? AND term IN ({marks})",
            [object_id, *terms],
        ).fetchall()
        return {
            "useful_weight": sum(float(r["useful_weight"]) for r in rows),
            "unhelpful_weight": sum(float(r["unhelpful_weight"]) for r in rows),
            "matched_terms": [r["term"] for r in rows],
        }

    def context_feedback_for_handle(self, handle: str, limit: int = 500):
        return self.conn.execute(
            "SELECT * FROM context_feedback WHERE handle=? ORDER BY seq ASC LIMIT ?", (handle, int(limit))
        ).fetchall()

    def create_episode(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO work_episodes(id,task,context_handle,base_revision,backend_binding,compiler_fingerprint,status,created_at,closed_at,outcome_json)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (value["id"], value["task"], value.get("context_handle"), value["base_revision"], value["backend_binding"],
             value["compiler_fingerprint"], value.get("status", "active"), value["created_at"], value.get("closed_at"),
             json.dumps(value.get("outcome") or {}, sort_keys=True)),
        )
        self.conn.commit()

    def episode(self, episode_id: str):
        return self.conn.execute("SELECT * FROM work_episodes WHERE id=?", (episode_id,)).fetchone()

    def episode_links(self, episode_id: str, limit: int = 1000):
        return self.conn.execute("SELECT * FROM episode_links WHERE episode_id=? ORDER BY seq ASC LIMIT ?", (episode_id, int(limit))).fetchall()

    def episodes_for_ref(self, ref_id: str):
        return self.conn.execute("SELECT DISTINCT episode_id FROM episode_links WHERE ref_id=? ORDER BY episode_id", (ref_id,)).fetchall()

    def append_episode_link(self, episode_id: str, kind: str, ref_id: str | None, revision: str, details: dict, created_at: str) -> int:
        if not self.episode(episode_id):
            raise KeyError(episode_id)
        cur = self.conn.execute(
            "INSERT INTO episode_links(episode_id,kind,ref_id,revision,details_json,created_at) VALUES(?,?,?,?,?,?)",
            (episode_id, kind, ref_id, revision, json.dumps(details, sort_keys=True), created_at),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def close_episode(self, episode_id: str, status: str, outcome: dict, closed_at: str) -> None:
        cur = self.conn.execute(
            "UPDATE work_episodes SET status=?,outcome_json=?,closed_at=? WHERE id=?",
            (status, json.dumps(outcome or {}, sort_keys=True), closed_at, episode_id),
        )
        if cur.rowcount != 1:
            raise KeyError(episode_id)
        self.conn.commit()

    def active_episode_for_context(self, handle: str):
        rows = self.conn.execute(
            "SELECT * FROM work_episodes WHERE context_handle=? AND status='active' ORDER BY created_at DESC LIMIT 2",
            (handle,),
        ).fetchall()
        return rows[0] if len(rows) == 1 else None

    def append_context_fault(self, handle: str, page_id: str, object_id: str, path: str, source_bytes: int, authority_bytes_read: int, revision: str, episode_id: str | None, fetched_at: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO context_faults(handle,page_id,object_id,path,source_bytes,authority_bytes_read,revision,episode_id,fetched_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (handle,page_id,object_id,path,int(source_bytes),int(authority_bytes_read),revision,episode_id,fetched_at),
        )
        return int(cur.lastrowid)

    def context_faults_for_handle(self, handle: str, limit: int = 5000):
        return self.conn.execute(
            "SELECT * FROM context_faults WHERE handle=? ORDER BY seq ASC LIMIT ?", (handle,int(limit))
        ).fetchall()

    def context_faults_for_episode(self, episode_id: str, limit: int = 5000):
        return self.conn.execute(
            "SELECT * FROM context_faults WHERE episode_id=? ORDER BY seq ASC LIMIT ?", (episode_id,int(limit))
        ).fetchall()

    def append_causal_edge(self, source_kind: str, source_ref: str, relation: str, target_kind: str, target_ref: str, revision: str, details: dict, created_at: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO causal_edges(source_kind,source_ref,relation,target_kind,target_ref,revision,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (source_kind,source_ref,relation,target_kind,target_ref,revision,json.dumps(details or {},sort_keys=True),created_at),
        )
        return int(cur.lastrowid)

    def causal_edges_for_ref(self, ref_id: str, limit: int = 1000):
        return self.conn.execute(
            "SELECT * FROM causal_edges WHERE source_ref=? OR target_ref=? ORDER BY seq ASC LIMIT ?", (ref_id,ref_id,int(limit))
        ).fetchall()

    def causal_edges_for_revision(self, revision: str, limit: int = 1000):
        return self.conn.execute(
            "SELECT * FROM causal_edges WHERE revision=? ORDER BY seq ASC LIMIT ?", (revision,int(limit))
        ).fetchall()

    def create_hypothesis(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO hypotheses(id,episode_id,task,statement,status,prior_confidence,current_confidence,base_revision,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value.get("episode_id"),value["task"],value["statement"],value.get("status","active"),
             float(value.get("prior_confidence",0.5)),float(value.get("current_confidence",value.get("prior_confidence",0.5))),
             value["base_revision"],value["created_at"],value.get("updated_at",value["created_at"])),
        ); self.conn.commit()

    def hypothesis(self, hypothesis_id: str):
        return self.conn.execute("SELECT * FROM hypotheses WHERE id=?",(hypothesis_id,)).fetchone()

    def hypotheses(self, episode_id: str | None = None, status: str | None = None, limit: int = 100):
        clauses=[]; args=[]
        if episode_id is not None: clauses.append("episode_id=?"); args.append(episode_id)
        if status is not None: clauses.append("status=?"); args.append(status)
        where=(" WHERE "+" AND ".join(clauses)) if clauses else ""
        return self.conn.execute(f"SELECT * FROM hypotheses{where} ORDER BY updated_at DESC LIMIT ?",[*args,int(limit)]).fetchall()

    def update_hypothesis(self, hypothesis_id: str, *, status: str | None = None, confidence: float | None = None, updated_at: str) -> None:
        row=self.hypothesis(hypothesis_id)
        if not row: raise KeyError(hypothesis_id)
        self.conn.execute("UPDATE hypotheses SET status=?,current_confidence=?,updated_at=? WHERE id=?",
                          (status or row["status"],float(row["current_confidence"] if confidence is None else confidence),updated_at,hypothesis_id))
        self.conn.commit()

    def link_hypothesis_evidence(self, hypothesis_id: str, evidence_id: str | None, polarity: str, weight: float, note: str | None, revision: str, created_at: str) -> int:
        if not self.hypothesis(hypothesis_id): raise KeyError(hypothesis_id)
        cur=self.conn.execute("INSERT INTO hypothesis_evidence(hypothesis_id,evidence_id,polarity,weight,note,revision,created_at) VALUES(?,?,?,?,?,?,?)",
                              (hypothesis_id,evidence_id,polarity,float(weight),note,revision,created_at))
        self.conn.commit(); return int(cur.lastrowid)

    def hypothesis_evidence(self, hypothesis_id: str):
        return self.conn.execute("SELECT * FROM hypothesis_evidence WHERE hypothesis_id=? ORDER BY seq",(hypothesis_id,)).fetchall()

    def create_experiment(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO experiments(id,hypothesis_id,episode_id,description,discriminator,status,capability,expected_json,result_json,base_revision,created_at,completed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value.get("hypothesis_id"),value.get("episode_id"),value["description"],value.get("discriminator"),
             value.get("status","planned"),value.get("capability"),json.dumps(value.get("expected") or {},sort_keys=True),
             json.dumps(value.get("result") or {},sort_keys=True),value["base_revision"],value["created_at"],value.get("completed_at")))
        self.conn.commit()

    def experiment(self, experiment_id: str):
        return self.conn.execute("SELECT * FROM experiments WHERE id=?",(experiment_id,)).fetchone()

    def experiments_for_hypothesis(self, hypothesis_id: str, limit: int = 100):
        return self.conn.execute("SELECT * FROM experiments WHERE hypothesis_id=? ORDER BY created_at LIMIT ?",(hypothesis_id,int(limit))).fetchall()

    def complete_experiment(self, experiment_id: str, status: str, result: dict, completed_at: str) -> None:
        cur=self.conn.execute("UPDATE experiments SET status=?,result_json=?,completed_at=? WHERE id=?",
                              (status,json.dumps(result or {},sort_keys=True),completed_at,experiment_id))
        if cur.rowcount != 1: raise KeyError(experiment_id)
        self.conn.commit()

    def append_event(self, event: EventRecord) -> int:
        cur = self.conn.execute(
            """INSERT INTO events(kind,path,observed_at,revision_before,revision_after,old_digest,new_digest,source,details_json)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (event.kind,event.path,event.observed_at,event.revision_before,event.revision_after,event.old_digest,event.new_digest,event.source,json.dumps(event.details)),
        )
        return int(cur.lastrowid)

    def events_since(self, seq: int = 0, limit: int = 200):
        return self.conn.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (seq, limit)).fetchall()

    def latest_event_seq(self) -> int:
        row = self.conn.execute("SELECT MAX(seq) FROM events").fetchone()
        return int(row[0] or 0)

    def append_activity(self, value: dict) -> int:
        cur=self.conn.execute(
            """INSERT INTO activity_events(kind,category,agent_id,episode_id,ref_id,path,revision,status,summary,data_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (value.get("kind") or "activity", value.get("category") or "workspace", value.get("agent_id"), value.get("episode_id"),
             value.get("ref_id"), value.get("path"), value.get("revision") or "none", value.get("status") or "info",
             value.get("summary") or value.get("kind") or "activity", json.dumps(value.get("data") or {},sort_keys=True), value.get("created_at") or ""),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def activity_since(self, seq: int = 0, limit: int = 500):
        return self.conn.execute("SELECT * FROM activity_events WHERE seq>? ORDER BY seq LIMIT ?",(int(seq),int(limit))).fetchall()

    def recent_activity(self, limit: int = 200, *, agent_id: str | None = None):
        if agent_id is None:
            rows=self.conn.execute("SELECT * FROM activity_events ORDER BY seq DESC LIMIT ?",(int(limit),)).fetchall()
        else:
            rows=self.conn.execute("SELECT * FROM activity_events WHERE agent_id=? ORDER BY seq DESC LIMIT ?",(agent_id,int(limit))).fetchall()
        return list(reversed(rows))

    def activity_bounds(self) -> tuple[int, int]:
        row=self.conn.execute("SELECT COALESCE(MIN(seq),0),COALESCE(MAX(seq),0) FROM activity_events").fetchone()
        return int(row[0] or 0), int(row[1] or 0)

    def latest_activity_seq(self) -> int:
        row=self.conn.execute("SELECT MAX(seq) FROM activity_events").fetchone()
        return int(row[0] or 0)

    def create_epistemic_item(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO epistemic_items(id,kind,statement,status,confidence,scope,agent_id,episode_id,base_revision,provenance_json,invalidation_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value["kind"],value["statement"],value["status"],value.get("confidence"),value.get("scope") or "workspace",
             value.get("agent_id"),value.get("episode_id"),value["base_revision"],json.dumps(value.get("provenance") or {},sort_keys=True),
             json.dumps(value.get("invalidation_conditions") or [],sort_keys=True),value["created_at"],value["updated_at"]),
        )
        self.conn.commit()

    def epistemic_item(self, item_id: str):
        return self.conn.execute("SELECT * FROM epistemic_items WHERE id=?",(item_id,)).fetchone()

    def epistemic_items(self, *, kind: str | None = None, status: str | None = None, agent_id: str | None = None, limit: int = 200):
        where=[]; args=[]
        if kind is not None: where.append("kind=?"); args.append(kind)
        if status is not None: where.append("status=?"); args.append(status)
        if agent_id is not None: where.append("(agent_id IS NULL OR agent_id=?)"); args.append(agent_id)
        sql="SELECT * FROM epistemic_items"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY updated_at DESC LIMIT ?"
        return self.conn.execute(sql,(*args,int(limit))).fetchall()

    def update_epistemic_item(self, item_id: str, *, status: str | None = None, confidence: float | None = None, updated_at: str, provenance: dict | None = None) -> None:
        row=self.epistemic_item(item_id)
        if not row: raise KeyError(item_id)
        values={"status":status if status is not None else row["status"],"confidence":confidence if confidence is not None else row["confidence"],
                "provenance_json":json.dumps(provenance,sort_keys=True) if provenance is not None else row["provenance_json"]}
        self.conn.execute("UPDATE epistemic_items SET status=?,confidence=?,provenance_json=?,updated_at=? WHERE id=?",
                          (values["status"],values["confidence"],values["provenance_json"],updated_at,item_id))
        self.conn.commit()

    def create_project_memory(self, value: dict) -> None:
        self.conn.execute("""INSERT INTO project_memories(id,kind,statement,status,scope,agent_id,episode_id,base_revision,confidence,provenance_json,evidence_json,valid_until_revision,supersedes,invalidated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value["kind"],value["statement"],value.get("status","active"),value.get("scope","workspace"),value.get("agent_id"),value.get("episode_id"),value["base_revision"],value.get("confidence"),json.dumps(value.get("provenance") or {},ensure_ascii=False),json.dumps(value.get("evidence_ids") or [],ensure_ascii=False),value.get("valid_until_revision"),value.get("supersedes"),value.get("invalidated_by"),value["created_at"],value["updated_at"]))
        self.conn.commit()

    def project_memory(self, memory_id: str):
        return self.conn.execute("SELECT * FROM project_memories WHERE id=?",(memory_id,)).fetchone()

    def find_active_memory(self, kind: str, statement: str, agent_id: str | None, base_revision: str):
        if agent_id is None:
            return self.conn.execute("SELECT * FROM project_memories WHERE kind=? AND statement=? AND agent_id IS NULL AND base_revision=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
                                     (kind,statement,base_revision)).fetchone()
        return self.conn.execute("SELECT * FROM project_memories WHERE kind=? AND statement=? AND agent_id=? AND base_revision=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
                                 (kind,statement,agent_id,base_revision)).fetchone()

    def project_memories(self, *, kind: str | None=None, status: str | None="active", agent_id: str | None=None, limit: int=200):
        sql="SELECT * FROM project_memories WHERE 1=1"; args=[]
        if kind is not None: sql+=" AND kind=?"; args.append(kind)
        if status is not None: sql+=" AND status=?"; args.append(status)
        if agent_id is not None: sql+=" AND (agent_id=? OR agent_id IS NULL)"; args.append(agent_id)
        sql+=" ORDER BY updated_at DESC LIMIT ?"; args.append(int(limit))
        return self.conn.execute(sql,tuple(args)).fetchall()

    def update_project_memory(self, memory_id: str, *, status: str | None=None, confidence: float | None=None, invalidated_by: str | None=None, updated_at: str):
        row=self.project_memory(memory_id)
        if not row: raise KeyError(memory_id)
        self.conn.execute("UPDATE project_memories SET status=?,confidence=?,invalidated_by=?,updated_at=? WHERE id=?",
            (status if status is not None else row["status"],confidence if confidence is not None else row["confidence"],invalidated_by if invalidated_by is not None else row["invalidated_by"],updated_at,memory_id))
        self.conn.commit()

    def append_runtime_event(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO runtime_events(id,trace_id,span_id,parent_span_id,kind,name,status,path,symbol_id,agent_id,episode_id,revision,started_at,duration_ms,attributes_json,source)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value.get("trace_id"),value.get("span_id"),value.get("parent_span_id"),value.get("kind") or "runtime",
             value.get("name") or "runtime-event",value.get("status") or "observed",value.get("path"),value.get("symbol_id"),value.get("agent_id"),
             value.get("episode_id"),value.get("revision") or "none",value.get("started_at") or "",value.get("duration_ms"),
             json.dumps(value.get("attributes") or {},sort_keys=True),value.get("source") or "runtime"),
        )
        self.conn.commit()

    def runtime_event(self, event_id: str):
        return self.conn.execute("SELECT * FROM runtime_events WHERE id=?",(event_id,)).fetchone()

    def runtime_events(self, *, trace_id: str | None = None, agent_id: str | None = None, limit: int = 500):
        where=[]; args=[]
        if trace_id is not None: where.append("trace_id=?"); args.append(trace_id)
        if agent_id is not None: where.append("agent_id=?"); args.append(agent_id)
        sql="SELECT * FROM runtime_events"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY started_at DESC LIMIT ?"
        return self.conn.execute(sql,(*args,int(limit))).fetchall()

    def replace_relations(self, relations: Iterable[RelationRecord]) -> None:
        self.conn.execute("DELETE FROM relations")
        for r in relations:
            self.conn.execute(
                "INSERT OR REPLACE INTO relations(source_id,target_id,kind,trust,evidence) VALUES(?,?,?,?,?)",
                (r.source_id, r.target_id, r.kind, r.trust, r.evidence),
            )

    def sync_relations(self, relations: Iterable[RelationRecord]) -> dict:
        """Set-diff the project relation graph and write only changed edges."""
        incoming = {(r.source_id,r.target_id,r.kind): r for r in relations}
        current_rows = self.conn.execute("SELECT * FROM relations").fetchall()
        current = {(r["source_id"],r["target_id"],r["kind"]): r for r in current_rows}
        inserted = updated = unchanged = 0
        for key, r in incoming.items():
            row = current.get(key)
            if row is None:
                self.conn.execute(
                    "INSERT INTO relations(source_id,target_id,kind,trust,evidence) VALUES(?,?,?,?,?)",
                    (r.source_id,r.target_id,r.kind,r.trust,r.evidence),
                )
                inserted += 1
            elif row["trust"] != r.trust or row["evidence"] != r.evidence:
                self.conn.execute(
                    "UPDATE relations SET trust=?,evidence=? WHERE source_id=? AND target_id=? AND kind=?",
                    (r.trust,r.evidence,r.source_id,r.target_id,r.kind),
                )
                updated += 1
            else:
                unchanged += 1
        deleted_keys = set(current) - set(incoming)
        if deleted_keys:
            self.conn.executemany(
                "DELETE FROM relations WHERE source_id=? AND target_id=? AND kind=?",
                list(deleted_keys),
            )
        return {"inserted": inserted, "updated": updated, "deleted": len(deleted_keys), "unchanged": unchanged, "total": len(incoming)}

    def commit(self) -> None:
        self.conn.commit()

    def file_by_path(self, path: str):
        return self.conn.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()

    def file_by_id(self, object_id: str):
        return self.conn.execute("SELECT * FROM files WHERE id=?", (object_id,)).fetchone()

    def symbol_by_id(self, object_id: str):
        return self.conn.execute("SELECT * FROM symbols WHERE id=?", (object_id,)).fetchone()

    def diagnostic_by_id(self, object_id: str):
        return self.conn.execute("SELECT * FROM diagnostics WHERE id=?", (object_id,)).fetchone()

    def symbols_named(self, name: str):
        q = f"%{name.lower()}%"
        return self.conn.execute(
            "SELECT * FROM symbols WHERE lower(name) LIKE ? OR lower(qualified_name) LIKE ? LIMIT 100", (q, q)
        ).fetchall()

    def symbols_for_file(self, file_id: str):
        return self.conn.execute("SELECT * FROM symbols WHERE file_id=? ORDER BY start_line", (file_id,)).fetchall()

    def all_symbols(self):
        return self.conn.execute("SELECT * FROM symbols ORDER BY path,start_line").fetchall()

    def all_files(self):
        return self.conn.execute("SELECT * FROM files ORDER BY path").fetchall()

    def all_diagnostics(self):
        return self.conn.execute("SELECT * FROM diagnostics ORDER BY path,line,column").fetchall()

    def diagnostics_for_path(self, path: str):
        return self.conn.execute("SELECT * FROM diagnostics WHERE path=? ORDER BY line,column", (path,)).fetchall()

    def relations_for(self, object_id: str):
        return self.conn.execute(
            "SELECT * FROM relations WHERE source_id=? OR target_id=?", (object_id, object_id)
        ).fetchall()

    def incoming_relations(self, object_id: str, kind: str | None = None):
        if kind:
            return self.conn.execute("SELECT * FROM relations WHERE target_id=? AND kind=?", (object_id, kind)).fetchall()
        return self.conn.execute("SELECT * FROM relations WHERE target_id=?", (object_id,)).fetchall()

    def search(self, query: str, limit: int = 30):
        terms = [t for t in query.replace('"', ' ').split() if t]
        if not terms:
            return []
        mode = self.get_meta("fts5", "0")
        if mode != "0":
            fts_q = " OR ".join(f'"{t}"' for t in terms[:10])
            try:
                return self.conn.execute(
                    """SELECT d.object_id,d.kind,d.path,d.title,bm25(search_fts,1.0,2.0,1.0) AS rank
                       FROM search_fts JOIN search_docs d ON d.rowid=search_fts.rowid
                       WHERE search_fts MATCH ? ORDER BY rank LIMIT ?""",
                    (fts_q, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                pass
        q = "%" + "%".join(terms[:4]).lower() + "%"
        return self.conn.execute(
            """SELECT id AS object_id,'symbol' AS kind,path,qualified_name AS title,0 AS rank
               FROM symbols WHERE lower(qualified_name) LIKE ? OR lower(path) LIKE ? LIMIT ?""",
            (q, q, limit),
        ).fetchall()

    def save_compile_cache(self, file_id: str, value: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO compile_cache(file_id,value_json) VALUES(?,?)", (file_id, json.dumps(value)))

    def load_compile_cache(self, file_id: str) -> dict | None:
        row = self.conn.execute("SELECT value_json FROM compile_cache WHERE file_id=?", (file_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def delete_compile_cache(self, file_id: str) -> None:
        self.conn.execute("DELETE FROM compile_cache WHERE file_id=?", (file_id,))

    # --- alpha.14 executive trajectory / milestone control ---
    def create_executive_trajectory(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO executive_trajectories(id,goal,agent_id,episode_id,status,base_revision,current_strategy,strategy_generation,budget_json,metrics_json,created_at,updated_at,closed_at,outcome_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value["goal"],value.get("agent_id"),value.get("episode_id"),value.get("status","active"),
             value["base_revision"],value.get("current_strategy","direct-analysis"),int(value.get("strategy_generation",0)),
             json.dumps(value.get("budget") or {},sort_keys=True),json.dumps(value.get("metrics") or {},sort_keys=True),
             value["created_at"],value["updated_at"],value.get("closed_at"),json.dumps(value.get("outcome") or {},sort_keys=True)),
        )
        self.conn.commit()

    def executive_trajectory(self, trajectory_id: str):
        return self.conn.execute("SELECT * FROM executive_trajectories WHERE id=?",(trajectory_id,)).fetchone()

    def executive_trajectories(self, *, status: str | None=None, agent_id: str | None=None, limit: int=100):
        sql="SELECT * FROM executive_trajectories WHERE 1=1"; args=[]
        if status is not None: sql+=" AND status=?"; args.append(status)
        if agent_id is not None: sql+=" AND agent_id=?"; args.append(agent_id)
        sql+=" ORDER BY updated_at DESC LIMIT ?"; args.append(int(limit))
        return self.conn.execute(sql,tuple(args)).fetchall()

    def update_executive_trajectory(self, trajectory_id: str, *, status: str | None=None, current_strategy: str | None=None,
                                    strategy_generation: int | None=None, metrics: dict | None=None, outcome: dict | None=None,
                                    updated_at: str, closed_at: str | None=None) -> None:
        row=self.executive_trajectory(trajectory_id)
        if not row: raise KeyError(trajectory_id)
        cur_metrics=json.loads(row["metrics_json"] or "{}")
        if metrics is not None: cur_metrics=metrics
        cur_outcome=json.loads(row["outcome_json"] or "{}")
        if outcome is not None: cur_outcome=outcome
        self.conn.execute(
            """UPDATE executive_trajectories SET status=?,current_strategy=?,strategy_generation=?,metrics_json=?,outcome_json=?,updated_at=?,closed_at=? WHERE id=?""",
            (status if status is not None else row["status"], current_strategy if current_strategy is not None else row["current_strategy"],
             int(strategy_generation if strategy_generation is not None else row["strategy_generation"]), json.dumps(cur_metrics,sort_keys=True),
             json.dumps(cur_outcome,sort_keys=True), updated_at, closed_at if closed_at is not None else row["closed_at"], trajectory_id),
        )
        self.conn.commit()

    def create_executive_milestone(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO executive_milestones(id,trajectory_id,title,postcondition,status,priority,dependencies_json,verifier_ref,rollback,base_revision,result_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value["trajectory_id"],value["title"],value["postcondition"],value.get("status","pending"),value.get("priority","high"),
             json.dumps(value.get("dependencies") or [],sort_keys=True),value.get("verifier_ref"),value.get("rollback"),value["base_revision"],
             json.dumps(value.get("result") or {},sort_keys=True),value["created_at"],value["updated_at"]),
        )
        self.conn.commit()

    def executive_milestone(self, milestone_id: str):
        return self.conn.execute("SELECT * FROM executive_milestones WHERE id=?",(milestone_id,)).fetchone()

    def executive_milestones(self, trajectory_id: str):
        return self.conn.execute("SELECT * FROM executive_milestones WHERE trajectory_id=? ORDER BY created_at,id",(trajectory_id,)).fetchall()

    def update_executive_milestone(self, milestone_id: str, *, status: str | None=None, verifier_ref: str | None=None,
                                   result: dict | None=None, updated_at: str) -> None:
        row=self.executive_milestone(milestone_id)
        if not row: raise KeyError(milestone_id)
        current_result=json.loads(row["result_json"] or "{}")
        if result is not None: current_result=result
        self.conn.execute(
            "UPDATE executive_milestones SET status=?,verifier_ref=?,result_json=?,updated_at=? WHERE id=?",
            (status if status is not None else row["status"], verifier_ref if verifier_ref is not None else row["verifier_ref"],
             json.dumps(current_result,sort_keys=True),updated_at,milestone_id),
        )
        self.conn.commit()

    def append_executive_event(self, value: dict) -> dict:
        trajectory_id=value["trajectory_id"]
        last=self.conn.execute("SELECT ordinal,record_hash FROM executive_events WHERE trajectory_id=? ORDER BY ordinal DESC LIMIT 1",(trajectory_id,)).fetchone()
        ordinal=int(last["ordinal"]+1) if last else 1
        previous_hash=last["record_hash"] if last else None
        from .executive import executive_event_hash
        record_hash=executive_event_hash(trajectory_id=trajectory_id,seq=ordinal,phase=value["phase"],operation=value["operation"],
                                         status=value["status"],revision=value["revision"],ref_id=value.get("ref_id"),
                                         data=value.get("data") or {},created_at=value["created_at"],previous_hash=previous_hash)
        self.conn.execute(
            """INSERT INTO executive_events(trajectory_id,ordinal,phase,operation,status,revision,ref_id,data_json,previous_hash,record_hash,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (trajectory_id,ordinal,value["phase"],value["operation"],value["status"],value["revision"],value.get("ref_id"),
             json.dumps(value.get("data") or {},sort_keys=True),previous_hash,record_hash,value["created_at"]),
        )
        self.conn.commit()
        return {**value,"ordinal":ordinal,"previous_hash":previous_hash,"record_hash":record_hash}

    def executive_events(self, trajectory_id: str, limit: int | None=None):
        sql="SELECT trajectory_id,ordinal AS seq,phase,operation,status,revision,ref_id,data_json,previous_hash,record_hash,created_at FROM executive_events WHERE trajectory_id=? ORDER BY ordinal ASC"
        if limit is None:
            return self.conn.execute(sql,(trajectory_id,)).fetchall()
        if int(limit)<1: raise ValueError("limit must be positive")
        return self.conn.execute(sql+" LIMIT ?",(trajectory_id,int(limit))).fetchall()

    def add_revision(self, r: Revision) -> None:
        self.conn.execute(
            "INSERT INTO revisions(id,parent_id,root_digest,reason,changed_paths,created_at) VALUES(?,?,?,?,?,?)",
            (r.id, r.parent_id, r.root_digest, r.reason, json.dumps(r.changed_paths), r.created_at),
        )
        self.set_meta("head_revision", r.id)

    def revision(self, revision_id: str):
        return self.conn.execute("SELECT * FROM revisions WHERE id=?", (revision_id,)).fetchone()

    def head_revision(self) -> str | None:
        return self.get_meta("head_revision")

    def save_json(self, table: str, id_: str, value: dict) -> None:
        if table not in _JSON_TABLES:
            raise ValueError("unsupported JSON table")
        self.conn.execute(f"INSERT OR REPLACE INTO {table}(id,value_json) VALUES(?,?)", (id_, json.dumps(value)))
        self.conn.commit()

    def load_json(self, table: str, id_: str) -> dict | None:
        if table not in _JSON_TABLES:
            raise ValueError("unsupported JSON table")
        row = self.conn.execute(f"SELECT value_json FROM {table} WHERE id=?", (id_,)).fetchone()
        return json.loads(row[0]) if row else None


    # --- alpha.9 agent isolation / concurrency primitives ---
    def create_agent_session(self, agent_id: str, name: str, created_at: str, metadata: dict | None = None) -> None:
        self.conn.execute(
            "INSERT INTO agent_sessions(id,name,status,created_at,updated_at,metadata_json) VALUES(?,?,'active',?,?,?)",
            (agent_id,name,created_at,created_at,json.dumps(metadata or {},sort_keys=True)),
        ); self.conn.commit()

    def agent_session(self, agent_id: str):
        return self.conn.execute("SELECT * FROM agent_sessions WHERE id=?",(agent_id,)).fetchone()

    def agent_sessions(self, status: str | None = None, limit: int = 100):
        if status is None:
            return self.conn.execute("SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT ?",(int(limit),)).fetchall()
        return self.conn.execute("SELECT * FROM agent_sessions WHERE status=? ORDER BY updated_at DESC LIMIT ?",(status,int(limit))).fetchall()

    def close_agent_session(self, agent_id: str, updated_at: str) -> None:
        self.conn.execute("UPDATE agent_sessions SET status='closed',updated_at=? WHERE id=?",(updated_at,agent_id)); self.conn.commit()

    def forget_agent_session(self, agent_id: str) -> dict:
        row=self.agent_session(agent_id)
        if not row: raise KeyError(agent_id)
        if row["status"]!="closed": raise ValueError("agent session must be closed before forgetting private cognitive state")
        counts={}
        for table in ("agent_context_utility","agent_observations","agent_notifications","agent_resident_objects","agent_hypothesis_beliefs","resource_leases"):
            counts[table]=int(self.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE agent_id=?",(agent_id,)).fetchone()[0])
        revoked=self.conn.execute("UPDATE approvals SET status='revoked' WHERE agent_id=? AND status='active'",(agent_id,)).rowcount
        self.conn.execute("DELETE FROM agent_sessions WHERE id=?",(agent_id,)); self.conn.commit()
        counts["revoked_approvals"]=int(revoked)
        return counts

    def record_agent_context_feedback(self, agent_id: str, object_id: str, verdict: str, weight: float, task_terms: list[str], revision: str, updated_at: str) -> None:
        if not self.agent_session(agent_id): raise KeyError(agent_id)
        if verdict not in {"used","unhelpful"}: raise ValueError("feedback verdict must be used or unhelpful")
        useful=float(weight) if verdict=="used" else 0.0; bad=float(weight) if verdict=="unhelpful" else 0.0
        for term in sorted(set(task_terms)):
            self.conn.execute(
                """INSERT INTO agent_context_utility(agent_id,object_id,term,useful_weight,unhelpful_weight,last_revision,updated_at)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(agent_id,object_id,term) DO UPDATE SET
                   useful_weight=MIN(10.0,agent_context_utility.useful_weight*0.92+excluded.useful_weight),
                   unhelpful_weight=MIN(10.0,agent_context_utility.unhelpful_weight*0.92+excluded.unhelpful_weight),
                   last_revision=excluded.last_revision,updated_at=excluded.updated_at""",
                (agent_id,object_id,term,useful,bad,revision,updated_at),
            )
        self.conn.commit()

    def agent_context_utility_for(self, agent_id: str, object_id: str, terms: list[str]) -> dict:
        terms=sorted(set(t for t in terms if t))
        if not terms: return {"useful_weight":0.0,"unhelpful_weight":0.0,"matched_terms":[]}
        marks=",".join("?" for _ in terms)
        rows=self.conn.execute(f"SELECT term,useful_weight,unhelpful_weight FROM agent_context_utility WHERE agent_id=? AND object_id=? AND term IN ({marks})",[agent_id,object_id,*terms]).fetchall()
        return {"useful_weight":sum(float(r["useful_weight"]) for r in rows),"unhelpful_weight":sum(float(r["unhelpful_weight"]) for r in rows),"matched_terms":[r["term"] for r in rows]}

    def acquire_lease(self, resource_kind: str, resource_id: str, agent_id: str, revision: str, acquired_at: str, expires_at: float, transaction_id: str | None = None) -> dict:
        if not self.agent_session(agent_id): raise KeyError(agent_id)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            import time as _time
            self.conn.execute("DELETE FROM resource_leases WHERE expires_at<=?",(_time.time(),))
            row=self.conn.execute("SELECT * FROM resource_leases WHERE resource_kind=? AND resource_id=?",(resource_kind,resource_id)).fetchone()
            if row and row["agent_id"]!=agent_id:
                self.conn.rollback(); return {"acquired":False,"conflict":dict(row)}
            self.conn.execute(
                "INSERT OR REPLACE INTO resource_leases(resource_kind,resource_id,agent_id,transaction_id,revision,acquired_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                (resource_kind,resource_id,agent_id,transaction_id,revision,acquired_at,float(expires_at)),
            )
            self.conn.commit(); return {"acquired":True,"resource_kind":resource_kind,"resource_id":resource_id,"agent_id":agent_id,"expires_at":float(expires_at)}
        except Exception:
            self.conn.rollback(); raise

    def release_lease(self, resource_kind: str, resource_id: str, agent_id: str) -> bool:
        cur=self.conn.execute("DELETE FROM resource_leases WHERE resource_kind=? AND resource_id=? AND agent_id=?",(resource_kind,resource_id,agent_id)); self.conn.commit(); return bool(cur.rowcount)

    def release_agent_leases(self, agent_id: str) -> int:
        cur=self.conn.execute("DELETE FROM resource_leases WHERE agent_id=?",(agent_id,)); self.conn.commit(); return int(cur.rowcount)

    def lease_rows(self, agent_id: str | None = None):
        import time as _time
        self.conn.execute("DELETE FROM resource_leases WHERE expires_at<=?",(_time.time(),)); self.conn.commit()
        if agent_id is None: return self.conn.execute("SELECT * FROM resource_leases ORDER BY resource_kind,resource_id").fetchall()
        return self.conn.execute("SELECT * FROM resource_leases WHERE agent_id=? ORDER BY resource_kind,resource_id",(agent_id,)).fetchall()

    def hypothesis_evidence_rows(self, hypothesis_id: str):
        return self.conn.execute("SELECT * FROM hypothesis_evidence WHERE hypothesis_id=? ORDER BY seq",(hypothesis_id,)).fetchall()

    def evidence_by_ids(self, ids: list[str]):
        ids=[x for x in ids if x]
        if not ids: return []
        marks=",".join("?" for _ in ids)
        return self.conn.execute(f"SELECT * FROM evidence WHERE id IN ({marks})",ids).fetchall()
    # --- alpha.10 coordination / agent residency / approvals ---
    def record_agent_observation(self, agent_id: str, path: str, digest: str | None, revision: str, kind: str = "source", object_id: str = "", observed_at: str = "") -> None:
        if not self.agent_session(agent_id): raise KeyError(agent_id)
        self.conn.execute(
            """INSERT INTO agent_observations(agent_id,path,object_id,digest,revision,kind,observed_at) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(agent_id,path,object_id) DO UPDATE SET digest=excluded.digest,revision=excluded.revision,kind=excluded.kind,observed_at=excluded.observed_at""",
            (agent_id,path,object_id or "",digest,revision,kind,observed_at),
        ); self.conn.commit()

    def agent_observations(self, agent_id: str | None = None, path: str | None = None):
        clauses=[]; args=[]
        if agent_id is not None: clauses.append("agent_id=?"); args.append(agent_id)
        if path is not None: clauses.append("path=?"); args.append(path)
        sql="SELECT * FROM agent_observations"+(" WHERE "+" AND ".join(clauses) if clauses else "")+" ORDER BY observed_at DESC"
        return self.conn.execute(sql,tuple(args)).fetchall()

    def append_agent_notification(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO agent_notifications(id,agent_id,kind,resource_kind,resource_id,revision,caused_by_transaction,data_json,status,created_at,acked_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (value["id"],value["agent_id"],value["kind"],value.get("resource_kind","path"),value["resource_id"],value["revision"],
             value.get("caused_by_transaction"),json.dumps(value.get("data") or {},sort_keys=True),value.get("status","pending"),value["created_at"],value.get("acked_at")),
        ); self.conn.commit()

    def agent_notifications(self, agent_id: str, status: str | None = "pending", limit: int = 200):
        if status is None:
            return self.conn.execute("SELECT * FROM agent_notifications WHERE agent_id=? ORDER BY created_at DESC LIMIT ?",(agent_id,int(limit))).fetchall()
        return self.conn.execute("SELECT * FROM agent_notifications WHERE agent_id=? AND status=? ORDER BY created_at DESC LIMIT ?",(agent_id,status,int(limit))).fetchall()

    def ack_agent_notification(self, notification_id: str, agent_id: str, acked_at: str) -> bool:
        cur=self.conn.execute("UPDATE agent_notifications SET status='acked',acked_at=? WHERE id=? AND agent_id=? AND status='pending'",(acked_at,notification_id,agent_id)); self.conn.commit(); return bool(cur.rowcount)

    def upsert_agent_resident(self, value: dict) -> None:
        self.conn.execute(
            """INSERT INTO agent_resident_objects(agent_id,object_id,kind,path,admitted_revision,source_digest,relevance,pinned,access_count,last_access_seq,admitted_at,last_touched_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(agent_id,object_id) DO UPDATE SET kind=excluded.kind,path=excluded.path,admitted_revision=excluded.admitted_revision,
                 source_digest=excluded.source_digest,relevance=MAX(agent_resident_objects.relevance,excluded.relevance),
                 pinned=MAX(agent_resident_objects.pinned,excluded.pinned),access_count=agent_resident_objects.access_count+1,
                 last_access_seq=excluded.last_access_seq,last_touched_at=excluded.last_touched_at""",
            (value["agent_id"],value["object_id"],value["kind"],value["path"],value["admitted_revision"],value.get("source_digest"),
             float(value.get("relevance",0.0)),int(bool(value.get("pinned"))),int(value.get("access_count",1)),int(value.get("last_access_seq",0)),
             value["admitted_at"],value["last_touched_at"]),
        ); self.conn.commit()

    def agent_resident_rows(self, agent_id: str):
        return self.conn.execute("SELECT * FROM agent_resident_objects WHERE agent_id=? ORDER BY pinned DESC,last_access_seq DESC,relevance DESC,object_id",(agent_id,)).fetchall()

    def delete_agent_resident(self, agent_id: str, object_id: str) -> None:
        self.conn.execute("DELETE FROM agent_resident_objects WHERE agent_id=? AND object_id=?",(agent_id,object_id)); self.conn.commit()

    def upsert_agent_hypothesis_belief(self, value: dict) -> None:
        if not self.agent_session(value["agent_id"]): raise KeyError(value["agent_id"])
        if not self.hypothesis(value["hypothesis_id"]): raise KeyError(value["hypothesis_id"])
        self.conn.execute(
            """INSERT INTO agent_hypothesis_beliefs(agent_id,hypothesis_id,stance,confidence,rationale,base_revision,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(agent_id,hypothesis_id) DO UPDATE SET stance=excluded.stance,confidence=excluded.confidence,rationale=excluded.rationale,base_revision=excluded.base_revision,updated_at=excluded.updated_at""",
            (value["agent_id"],value["hypothesis_id"],value["stance"],float(value["confidence"]),value.get("rationale"),value["base_revision"],value["updated_at"]),
        ); self.conn.commit()

    def agent_hypothesis_belief(self, agent_id: str, hypothesis_id: str):
        return self.conn.execute("SELECT * FROM agent_hypothesis_beliefs WHERE agent_id=? AND hypothesis_id=?",(agent_id,hypothesis_id)).fetchone()

    def agent_hypothesis_beliefs(self, agent_id: str, limit: int = 200):
        return self.conn.execute("SELECT * FROM agent_hypothesis_beliefs WHERE agent_id=? ORDER BY updated_at DESC LIMIT ?",(agent_id,int(limit))).fetchall()

    def create_approval(self, value: dict) -> None:
        self.conn.execute(
            "INSERT INTO approvals(id,action,resource,agent_id,granted_by,status,expires_at,created_at,metadata_json) VALUES(?,?,?,?,?,'active',?,?,?)",
            (value["id"],value["action"],value.get("resource"),value.get("agent_id"),value["granted_by"],float(value["expires_at"]),value["created_at"],json.dumps(value.get("metadata") or {},sort_keys=True)),
        ); self.conn.commit()

    def consume_approval(self, approval_id: str, *, action: str, resource: str | None, agent_id: str | None, consumed_at: str, now_ts: float) -> dict | None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row=self.conn.execute("SELECT * FROM approvals WHERE id=?",(approval_id,)).fetchone()
            if not row or row["status"]!="active" or float(row["expires_at"])<=float(now_ts): self.conn.rollback(); return None
            if row["action"]!=action or (row["resource"] is not None and row["resource"]!=resource) or (row["agent_id"] is not None and row["agent_id"]!=agent_id): self.conn.rollback(); return None
            self.conn.execute("UPDATE approvals SET status='consumed',consumed_at=? WHERE id=?",(consumed_at,approval_id)); self.conn.commit(); return dict(row)
        except Exception:
            self.conn.rollback(); raise
    def create_invariant(self, value: dict) -> None:
        self.conn.execute("INSERT INTO project_invariants(id,statement,severity,status,base_revision,created_at,updated_at,metadata_json) VALUES(?,?,?,?,?,?,?,?)",
                          (value["id"],value["statement"],value["severity"],value["status"],value["base_revision"],value["created_at"],value["updated_at"],json.dumps(value.get("metadata") or {},sort_keys=True))); self.conn.commit()

    def invariant(self, invariant_id: str):
        return self.conn.execute("SELECT * FROM project_invariants WHERE id=?",(invariant_id,)).fetchone()

    def update_invariant(self, invariant_id: str, status: str, updated_at: str) -> None:
        self.conn.execute("UPDATE project_invariants SET status=?,updated_at=? WHERE id=?",(status,updated_at,invariant_id)); self.conn.commit()

    def link_invariant(self, invariant_id: str, ref_kind: str, ref_id: str, relation: str, revision: str, details: dict, created_at: str) -> int:
        if not self.invariant(invariant_id): raise KeyError(invariant_id)
        cur=self.conn.execute("INSERT INTO invariant_links(invariant_id,ref_kind,ref_id,relation,revision,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                              (invariant_id,ref_kind,ref_id,relation,revision,json.dumps(details or {},sort_keys=True),created_at)); self.conn.commit(); return int(cur.lastrowid)

    def invariant_links(self, invariant_id: str):
        return self.conn.execute("SELECT * FROM invariant_links WHERE invariant_id=? ORDER BY seq",(invariant_id,)).fetchall()


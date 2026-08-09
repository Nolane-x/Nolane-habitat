from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from difflib import SequenceMatcher
from pathlib import Path

from ..model import ContextObject, ContextSlice, to_dict
from ..util import stable_id, utc_now

_TASK_CLASSES = {
    "ui": {"ui", "html", "css", "button", "form", "layout", "screen", "page", "visual", "frontend", "browser", "click"},
    "test": {"test", "tests", "pytest", "unittest", "jest", "vitest", "failing", "failure", "regression", "verify"},
    "build": {"build", "compile", "package", "dependency", "install", "maven", "gradle", "npm", "bundle"},
    "documentation": {"document", "documentation", "readme", "docs", "guide", "spec", "plan"},
    "implementation": {"implement", "implementation", "logic", "function", "method", "class", "code", "backend", "bug", "fix", "validate", "validation", "refactor"},
}
_STOP = {"the","a","an","and","or","to","in","of","for","is","are","it","this","that","where","what","how","with","after","before","please","find","make","change", "và","hoặc","của","cho","trong","là","này","đó","hãy","với","sau","trước","tìm","làm"}
_REL_WEIGHT = {"calls": 0.62, "imports": 0.44, "imports_symbol": 0.56, "contains": 0.46, "tests": 0.70,
               "renders": 0.52, "handles_event": 0.64}
_TRUST_BONUS = {"exact": 0.09, "semantic": 0.075, "parser": 0.04, "derived": 0.0, "heuristic": -0.06}
_TRUST_CAP = {"exact": 1.0, "semantic": 0.94, "parser": 0.78, "derived": 0.52, "heuristic": 0.30}


def _task_terms(task: str) -> list[str]:
    out=[]
    for token in re.findall(r"[^\W\d_][\w\-]*", task, flags=re.UNICODE):
        token=token.casefold().strip("_-")
        if token and token not in _STOP:
            out.append(token)
    return out


def _identifier_terms(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").replace("-", " ")
    return [x.casefold() for x in re.findall(r"\w+", value, flags=re.UNICODE) if not x.isdigit()]


def _near(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return 0.92
    return SequenceMatcher(None, a, b).ratio()


def _is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    name = Path(p).name
    return "/tests/" in f"/{p}" or name.startswith("test_") or name.endswith("_test.py") or ".test." in name or ".spec." in name


class ContextCompiler:
    """Task-aware, evidence-preserving context compiler.

    It intentionally combines several weakly-correlated candidate lanes instead of treating
    embeddings or full-text search as a universal oracle. Exact source remains paged behind
    object handles; this compiler returns orientation state, not a hidden source copy.
    """

    def __init__(self, workspace):
        self.workspace = workspace
        self.store = workspace.store

    def classify(self, task: str) -> str:
        terms = set(_task_terms(task))
        scores = {name: len(terms & words) for name, words in _TASK_CLASSES.items()}
        if terms & {"fix", "implement", "implemented", "refactor", "bug"}:
            if scores.get("ui", 0) >= 2:
                return "ui"
            return "implementation"
        priority = {"implementation": 5, "ui": 4, "test": 3, "build": 2, "documentation": 1}
        best = max(scores, key=lambda name: (scores[name], priority.get(name, 0)))
        return best if scores[best] else "generic"

    def _symbol_score(self, row, terms: list[str], task_class: str) -> float:
        if not terms:
            return 0.0
        name_terms = _identifier_terms(row["qualified_name"])
        path_terms = _identifier_terms(row["path"])
        matched = []
        for term in terms:
            best_name = max((_near(term, nt) for nt in name_terms), default=0.0)
            best_path = max((_near(term, pt) for pt in path_terms), default=0.0)
            matched.append(max(best_name, best_path * 0.48))
        strong = [x for x in matched if x >= 0.62]
        # Structural type alone is not task evidence.  Earlier revisions gave every function/class an
        # implementation bonus even when none of the task concepts matched, which caused unrelated
        # helper symbols to fill a context budget.  Require at least one content match before task-class
        # or trust bonuses can promote the symbol.
        if not strong:
            return 0.0
        score = sum(strong) / len(terms) + (len(strong) / len(terms)) * 0.18
        if task_class == "implementation" and row["kind"] in {"function", "method", "class", "interface", "type"}:
            score += 0.24
        if task_class == "ui" and row["kind"] in {"ui-element", "css-rule"}:
            score += 0.25
        if task_class != "ui" and row["kind"] == "ui-element":
            score -= 0.12
        if task_class == "test" and _is_test_path(row["path"]):
            score += 0.28
        score += _TRUST_BONUS.get(row["trust"], 0.0)
        return max(0.0, min(score, 1.25))

    def _add_candidate(self, candidates: dict, oid: str, score: float, reason: str, lane: str, kind: str, path: str, trust: str | None = None):
        if score <= 0:
            return
        old = candidates.get(oid)
        value = {"object_id": oid, "score": score, "reason": reason, "lane": lane, "kind": kind, "path": path, "trust": trust}
        if old is None:
            candidates[oid] = value
        else:
            # Independent evidence lanes should compound, but never explode linearly.
            combined = max(old["score"], score) + min(old["score"], score) * 0.12
            if combined > old["score"]:
                value["score"] = combined
                value["reason"] = old["reason"] + "; " + reason
                value["lane"] = old["lane"] + "+" + lane if lane not in old["lane"] else old["lane"]
                candidates[oid] = value

    def _content_terms(self, task: str) -> list[str]:
        terms = _task_terms(task)
        intent_terms = {"implement","implemented","implementation","logic","function","method","class","code","backend","fix","bug","test","tests","ui"}
        return [t for t in terms if t not in intent_terms] or terms

    def _primary_candidates(self, task: str, task_class: str, agent_id: str | None = None) -> dict[str, dict]:
        terms = _task_terms(task)
        candidates: dict[str, dict] = {}
        content_terms = self._content_terms(task)

        hits = self.store.search(" ".join(content_terms), limit=100)
        for i, hit in enumerate(hits):
            base = max(0.08, 0.76 - i / max(len(hits), 1) * 0.44)
            trust = None
            if hit["kind"] == "symbol":
                sr = self.store.symbol_by_id(hit["object_id"]); trust = sr["trust"] if sr else None
            elif hit["kind"] == "diagnostic":
                dr = self.store.diagnostic_by_id(hit["object_id"]); trust = dr["trust"] if dr else None
                if task_class in {"implementation", "test", "build"}: base += 0.12
            elif hit["kind"] == "evidence":
                er = self.store.evidence_by_id(hit["object_id"])
                # Resolved runtime evidence is historical audit data, not current task context. FTS rows
                # deliberately remain append-only/searchable for audit, so retrieval must enforce active state.
                if not er or not er["active"]:
                    continue
                trust = er["trust"]
                if er["severity"] in {"error","warning"}: base += 0.18
            self._add_candidate(candidates, hit["object_id"], base, "lexical index match", "lexical", hit["kind"], hit["path"], trust)

        # Persistent inverted symbol-term index bounds the structural lane. Repo growth should not
        # force a full symbol-table scan for every task. Fuzzy morphology is handled by the index
        # lookup itself, then the richer scorer ranks only the bounded candidates.
        for row in self.store.symbols_matching_terms(content_terms, limit=1200):
            score = self._symbol_score(row, content_terms, task_class)
            if score >= 0.20:
                self._add_candidate(candidates, row["id"], score, "indexed task-to-symbol structural match", "symbol", "symbol", row["path"], row["trust"])

        if task_class in {"test", "implementation"}:
            for row in self.store.all_files():
                if _is_test_path(row["path"]):
                    overlap = sum(1 for t in content_terms if t in row["path"].lower())
                    if not overlap:
                        continue
                    score = 0.24 + min(0.32, overlap * 0.10)
                    if task_class == "test": score += 0.20
                    self._add_candidate(candidates, row["id"], score, "test-file lane", "test", "file", row["path"], "derived")

        if task_class in {"implementation", "test", "build", "generic"}:
            for d in self.store.all_diagnostics():
                overlap = sum(1 for t in content_terms if t in (d["message"] + " " + d["path"]).lower())
                if overlap:
                    score = 0.36 + min(0.3, overlap * 0.12)
                    self._add_candidate(candidates, d["id"], score, "active diagnostic evidence", "diagnostic", "diagnostic", d["path"], d["trust"])

        # Runtime/verification evidence is first-class but never silently promoted to source truth.
        # Only active evidence with task overlap (or test/build relevance) gets a bounded lane.
        for e in self.store.active_evidence(limit=300):
            hay = ((e["summary"] or "") + " " + (e["path"] or "")).lower()
            overlap = sum(1 for t in content_terms if t in hay)
            if not overlap and not (task_class in {"test","build"} and e["kind"] == "test-failure"):
                continue
            score = 0.42 + min(0.34, overlap * 0.11) + (0.12 if e["severity"] == "error" else 0.05 if e["severity"] == "warning" else 0.0)
            self._add_candidate(candidates, e["id"], score, f"active runtime evidence:{e['kind']}", "evidence", "evidence", e["path"] or "", e["trust"])

        # Persistent residency is an attention prior, never an authority lane. Only fresh objects that
        # still overlap the current task (or are independently retrieved already) receive a bounded boost.
        # This prevents yesterday's working set from becoming today's confirmation bias.
        for resident in (self.store.agent_resident_rows(agent_id) if agent_id else self.store.resident_rows()):
            fr = self.store.file_by_path(resident["path"])
            if not fr or fr["digest"] != resident["source_digest"]:
                continue
            oid = resident["object_id"]; sr = self.store.symbol_by_id(oid); dr = self.store.diagnostic_by_id(oid); file_row = self.store.file_by_id(oid)
            task_score = 0.0; kind = resident["kind"]; trust = None
            if sr:
                task_score = self._symbol_score(sr, content_terms, task_class); kind = "symbol"; trust = sr["trust"]
            elif dr:
                hay = (dr["message"] + " " + dr["path"]).lower(); task_score = min(1.0, sum(1 for x in content_terms if x in hay) * 0.22); kind = "diagnostic"; trust = dr["trust"]
            elif file_row:
                hay = file_row["path"].lower(); task_score = min(1.0, sum(1 for x in content_terms if x in hay) * 0.18); kind = "file"; trust = "derived"
            else:
                continue
            if oid not in candidates and task_score < 0.20:
                continue
            memory_strength = min(0.20, float(resident["relevance"] or 0) * 0.08 + min(int(resident["access_count"] or 0), 5) * 0.015 + (0.05 if resident["pinned"] else 0.0))
            score = max(0.12, task_score * 0.52 + memory_strength)
            self._add_candidate(candidates, oid, score, "fresh resident working-set prior", "resident", kind, resident["path"], trust)
        return candidates

    def _expand_graph(self, candidates: dict[str, dict], task_class: str, max_roots: int = 8, depth: int = 2) -> None:
        ranked_roots = sorted(candidates.values(), key=lambda c: (-c["score"], c["path"], c["object_id"]))
        if task_class == "implementation":
            # Test bodies often repeat implementation identifiers and can create a self-reinforcing
            # lexical→test→implementation loop. Start causal expansion from production objects; tests
            # are then discovered as dependents through the graph rather than treated as equal roots.
            production = [c for c in ranked_roots if not _is_test_path(c["path"])]
            roots = (production or ranked_roots)[:max_roots]
        else:
            roots = ranked_roots[:max_roots]
        root_ids = {r["object_id"] for r in roots}
        queue = deque((r["object_id"], r["score"], 0, r["object_id"]) for r in roots)
        visited = set(root_ids)
        while queue:
            oid, parent_score, d, origin = queue.popleft()
            if d >= depth:
                continue
            for rel in self.store.relations_for(oid):
                neighbor = rel["target_id"] if rel["source_id"] == oid else rel["source_id"]
                sr = self.store.symbol_by_id(neighbor)
                fr = self.store.file_by_id(neighbor)
                if not sr and not fr:
                    continue
                row = sr or fr
                trust = rel["trust"]
                rel_weight = _REL_WEIGHT.get(rel["kind"], 0.30)
                score = parent_score * rel_weight * (0.78 if d else 1.0) + _TRUST_BONUS.get(trust, 0.0)
                # A weak relation may suggest where to look, but it cannot become strong confidence merely
                # by being traversed through the graph. Independent lexical/diagnostic/evidence lanes may
                # still lift the same object later.
                score = min(score, _TRUST_CAP.get(trust, 0.45))
                # A distinct semantic root may strengthen another already-discovered root. Do not let a
                # root reinforce itself through a two-edge round trip (A→B→A), which would create graph score loops.
                if neighbor not in visited or (neighbor in root_ids and neighbor != origin):
                    self._add_candidate(candidates, neighbor, score,
                                        f"dependency expansion:{rel['kind']} trust:{trust}", "graph",
                                        "symbol" if sr else "file", row["path"], sr["trust"] if sr else trust)
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, score, d + 1, origin))

    def _apply_utility_prior(self, candidates: dict[str, dict], task: str, agent_id: str | None = None) -> int:
        """Apply bounded task-local utility feedback to already-supported candidates only.

        Feedback is never allowed to create a candidate from nothing: lexical/semantic/graph/runtime
        evidence must first support the object. This keeps experience as an attention prior instead of
        turning prior agent behavior into source authority.
        """
        terms = self._content_terms(task)
        applied = 0
        for oid, candidate in candidates.items():
            utility = self.store.context_utility_for(oid, terms)
            agent_utility = self.store.agent_context_utility_for(agent_id, oid, terms) if agent_id else {"useful_weight":0.0,"unhelpful_weight":0.0,"matched_terms":[]}
            useful = float(utility.get("useful_weight", 0.0)) + min(4.0,float(agent_utility.get("useful_weight",0.0)))
            unhelpful = float(utility.get("unhelpful_weight", 0.0)) + min(4.0,float(agent_utility.get("unhelpful_weight",0.0)))
            total = useful + unhelpful
            matched_terms=sorted(set((utility.get("matched_terms") or [])+(agent_utility.get("matched_terms") or [])))
            if total <= 0 or not matched_terms:
                continue
            signal = (useful - unhelpful) / (total + 2.0)
            adjustment = max(-0.12, min(0.12, signal * 0.16))
            if abs(adjustment) < 0.005:
                continue
            candidate["score"] = max(0.0, min(1.5, float(candidate["score"]) + adjustment))
            direction = "useful" if adjustment > 0 else "unhelpful"
            candidate["reason"] = str(candidate.get("reason") or "") + f"; bounded context-utility prior:{direction}"
            lane = str(candidate.get("lane") or "")
            if "utility" not in lane.split("+"):
                candidate["lane"] = lane + "+utility" if lane else "utility"
            candidate["utility_prior"] = round(adjustment, 6)
            candidate["utility_terms"] = matched_terms
            if agent_id and agent_utility.get("matched_terms"):
                candidate["agent_utility_prior"] = agent_id
            applied += 1
        return applied

    def _select(self, candidates: dict[str, dict], task_class: str, budget: int) -> tuple[list[ContextObject], list[dict]]:
        ranked = sorted(candidates.values(), key=lambda c: (-c["score"], c["path"], c["object_id"]))
        selected: list[ContextObject] = []
        path_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        deferred: list[dict] = []
        per_path_cap = max(2, min(5, budget // 4 + 1))
        file_cap = max(2, budget // 3)

        for c in ranked:
            if path_counts[c["path"]] >= per_path_cap:
                deferred.append(c); continue
            if c["kind"] == "file" and type_counts["file"] >= file_cap:
                deferred.append(c); continue
            sr = self.store.symbol_by_id(c["object_id"])
            dr = self.store.diagnostic_by_id(c["object_id"])
            source_range = None
            otype = c["kind"]
            trust = c.get("trust")
            if sr:
                source_range = (sr["start_line"], sr["end_line"]); otype = "symbol"; trust = sr["trust"]
            elif dr:
                source_range = (dr["line"], dr["line"]) if dr["line"] else None; otype = "diagnostic"; trust = dr["trust"]
            selected.append(ContextObject(c["object_id"], otype, min(c["score"], 1.0), c["reason"], c["path"], source_range, c["lane"], trust))
            path_counts[c["path"]] += 1; type_counts[otype] += 1
            if len(selected) >= budget:
                break

        # Ensure task-specific evidence isn't crowded out by many symbols from one subsystem.
        if task_class == "test" and not any("test" in o.lane for o in selected):
            alt = next((c for c in ranked if "test" in c["lane"] and c["object_id"] not in {o.object_id for o in selected}), None)
            if alt and selected:
                selected[-1] = ContextObject(alt["object_id"], alt["kind"], min(alt["score"], 1.0), alt["reason"], alt["path"], None, alt["lane"], alt.get("trust"))
        return selected, ranked

    def compile(self, task: str, budget: int = 18, agent_id: str | None = None) -> ContextSlice:
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1 or budget > 200:
            raise ValueError("budget must be in [1, 200]")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        task_class = self.classify(task)
        candidates = self._primary_candidates(task, task_class, agent_id)
        self._expand_graph(candidates, task_class)
        utility_priors_applied = self._apply_utility_prior(candidates, task, agent_id)
        objects, ranked = self._select(candidates, task_class, budget)
        handle = stable_id("ctx", self.workspace.revision, task, utc_now())
        self.store.save_json("context_slices", handle, {
            "task": task,
            "revision": self.workspace.revision,
            "task_class": task_class,
            "ranked": ranked,
            "budget": budget,
            "selected_ids": [o.object_id for o in objects],
            "created_at": utc_now(),
            "agent_id": agent_id,
        })
        unknowns: list[str] = []
        if not objects:
            unknowns.append("No indexed object strongly matched the task; exact-source exploration may be required.")
        if any(o.trust == "heuristic" for o in objects):
            unknowns.append("Selected context includes heuristic objects; inspect exact source before consequential edits.")
        selected_paths = {o.path for o in objects if o.path}
        if any((self.store.file_by_path(p) and self.store.file_by_path(p)["index_truncated"]) for p in selected_paths):
            unknowns.append("Selected files include truncated lexical indexes; a missing lexical hit is not absence evidence.")
        if any((self.store.file_by_path(p) and not self.store.file_by_path(p)["parse_complete"]) for p in selected_paths):
            unknowns.append("Selected files include incomplete syntax parses; exact-source inspection may be required.")
        lane_counts = Counter()
        trust_counts = Counter()
        for o in objects:
            for lane in o.lane.split("+"):
                lane_counts[lane] += 1
            trust_counts[o.trust or "unknown"] += 1
        top_score = min(1.0, float(ranked[0]["score"])) if ranked else 0.0
        top_lanes = set()
        for c in ranked[: min(5, len(ranked))]:
            top_lanes.update(str(c.get("lane") or "").split("+"))
        content_terms=self._content_terms(task)
        evaluated_terms=content_terms[:64]
        coverage_truncated=len(content_terms)>len(evaluated_terms)
        supported_terms=[]
        term_paths: dict[str,set[str]] = {}
        for term in evaluated_terms:
            paths=set()
            for hit in self.store.search(term,limit=8):
                if hit["path"]:
                    paths.add(str(hit["path"]))
            if not paths:
                for row in self.store.symbols_matching_terms([term],limit=64):
                    tokens = _identifier_terms(row["qualified_name"]) + _identifier_terms(row["path"])
                    if any(_near(term, token) >= 0.76 for token in tokens):
                        paths.add(str(row["path"]))
                        if len(paths)>=8: break
            if paths:
                supported_terms.append(term); term_paths[term]=paths
        concept_coverage=(len(supported_terms)/len(evaluated_terms)) if evaluated_terms else 0.0
        path_support=Counter()
        for paths in term_paths.values():
            for path in paths:
                path_support[path]+=1
        coherent_count=max(path_support.values(), default=0)
        coherent_coverage=(coherent_count/len(evaluated_terms)) if evaluated_terms else 0.0
        if not objects or top_score < 0.28 or concept_coverage < 0.34:
            retrieval_confidence = "low"
        elif top_score >= 0.66 and concept_coverage >= 0.60 and (len(evaluated_terms) <= 1 or coherent_coverage >= 0.34) and len(top_lanes & {"symbol","graph","evidence","diagnostic","resident"}) >= 1:
            retrieval_confidence = "high"
        else:
            retrieval_confidence = "medium"
        abstention_recommended = not objects or retrieval_confidence == "low"
        if abstention_recommended:
            unknowns.append("Retrieval confidence is low; prefer explicit exploration or ask for a narrower target before loading broad source context.")
        decision_packet = {
            "objective": task,
            "revision": self.workspace.revision,
            "retrieval_confidence": retrieval_confidence,
            "top_candidate_score": round(top_score, 4),
            "concept_coverage": round(concept_coverage, 4),
            "concept_neighborhood_coverage": round(coherent_coverage, 4),
            "coverage_evaluated_concepts": len(evaluated_terms),
            "coverage_truncated": coverage_truncated,
            "supported_concepts": supported_terms,
            "unsupported_concepts": [x for x in evaluated_terms if x not in supported_terms],
            "abstention_recommended": abstention_recommended,
            "top_evidence_lanes": sorted(x for x in top_lanes if x),
            "context_utility_priors_applied": utility_priors_applied,
            "context_utility_is_non_authoritative": True,
            "inspect_first": [o.object_id for o in objects[: min(6, len(objects))]],
            "exact_source_required_before_mutation": [o.object_id for o in objects if o.trust in {"heuristic", "derived"}],
            "context_is_orientation_not_authority": True,
            "omitted_candidates": max(0, len(ranked) - len(objects)),
        }
        stored_slice = self.store.load_json("context_slices", handle) or {}
        stored_slice.update({
            "decision_packet": decision_packet,
            "unknowns": unknowns,
            "lane_counts": dict(lane_counts),
            "trust_counts": dict(trust_counts),
            "selected_ids": [o.object_id for o in objects],
        })
        self.store.save_json("context_slices", handle, stored_slice)
        return ContextSlice(task, self.workspace.revision, objects, unknowns,
                            max(0, len(ranked) - len(objects)), budget, task_class, handle, dict(lane_counts), dict(trust_counts), decision_packet)

    def refresh_slice(self, handle: str, budget: int | None = None) -> dict:
        """Recompile a stale/live task context and report the semantic delta.

        This is intentionally not an in-place mutation of the old handle: context packets are provenance-bound
        to the revision that produced them.  The returned handle is a new artifact with an explicit delta.
        """
        old = self.store.load_json("context_slices", handle)
        if not old:
            raise KeyError(handle)
        chosen_budget = int(budget if budget is not None else old.get("budget", 18))
        if chosen_budget < 1 or chosen_budget > 200:
            raise ValueError("budget must be in [1, 200]")
        old_ids = list(old.get("selected_ids") or [x.get("object_id") for x in old.get("ranked", [])[:chosen_budget] if x.get("object_id")])
        old_revision = old.get("revision")
        fresh = self.compile(old["task"], chosen_budget)
        new_ids = [o.object_id for o in fresh.objects]
        old_set, new_set = set(old_ids), set(new_ids)
        retained = [x for x in new_ids if x in old_set]
        added = [x for x in new_ids if x not in old_set]
        removed = [x for x in old_ids if x not in new_set]
        missing = [x for x in removed if not (self.store.symbol_by_id(x) or self.store.file_by_id(x) or self.store.diagnostic_by_id(x))]
        revision_delta = None
        if old_revision and self.store.revision(old_revision):
            revision_delta = self.workspace.diff_since(old_revision)
        return {
            "previous_handle": handle,
            "previous_revision": old_revision,
            "current_revision": self.workspace.revision,
            "context": to_dict(fresh),
            "delta": {
                "retained_object_ids": retained,
                "added_object_ids": added,
                "removed_object_ids": removed,
                "missing_object_ids": missing,
                "changed_paths": revision_delta.get("changed_paths", []) if revision_delta and revision_delta.get("reachable", True) else [],
                "revision_reachable": revision_delta.get("reachable", True) if revision_delta else old_revision == self.workspace.revision,
            },
        }

    def page(self, handle: str, offset: int = 0, limit: int = 20) -> dict:
        value = self.store.load_json("context_slices", handle)
        if not value:
            raise KeyError(handle)
        if value["revision"] != self.workspace.revision:
            return {"handle": handle, "stale": True, "compiled_revision": value["revision"], "current_revision": self.workspace.revision, "objects": []}
        ranked = value.get("ranked", [])
        page = ranked[offset: offset + limit]
        out = []
        for c in page:
            sr = self.store.symbol_by_id(c["object_id"])
            dr = self.store.diagnostic_by_id(c["object_id"])
            source_range = None
            kind = c["kind"]
            trust = c.get("trust")
            if sr:
                kind = "symbol"; source_range = [sr["start_line"], sr["end_line"]]; trust = sr["trust"]
            elif dr:
                kind = "diagnostic"; source_range = [dr["line"], dr["line"]] if dr["line"] else None; trust = dr["trust"]
            out.append({
                "object_id": c["object_id"], "object_type": kind, "relevance": min(c["score"], 1.0),
                "reason": c["reason"], "path": c["path"], "source_range": source_range,
                "lane": c["lane"], "trust": trust,
            })
        return {"handle": handle, "stale": False, "offset": offset, "limit": limit, "total": len(ranked), "objects": out,
                "next_offset": offset + len(out) if offset + len(out) < len(ranked) else None}

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from .runtime_correlation import correlate_runtime_fact
from .util import stable_id, utc_now

_EFFECT_KINDS = {
    "reads", "writes", "mutates", "returns", "throws", "awaits", "emits", "subscribes",
    "sends", "receives", "validates", "sanitizes", "authorizes", "db-query", "network-request",
    "env-read", "filesystem-write",
}


def _safe_unparse(node: ast.AST | None, limit: int = 180) -> str:
    if node is None:
        return ""
    try:
        text = ast.unparse(node)
    except Exception:
        text = node.__class__.__name__
    text = " ".join(text.split())
    return text[:limit]


def _name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    return _safe_unparse(node, 120)


def _classify_call(name: str, args: list[ast.AST]) -> list[tuple[str, str, dict]]:
    low = name.casefold()
    tail = low.rsplit(".", 1)[-1]
    out: list[tuple[str, str, dict]] = []
    if any(x in tail for x in ("validate", "verify", "check")):
        out.append(("validates", name, {}))
    if any(x in tail for x in ("sanitize", "normaliz", "escape", "clean")):
        out.append(("sanitizes", name, {}))
    if any(x in tail for x in ("authoriz", "permission", "allowed", "can_access", "can_edit")):
        out.append(("authorizes", name, {}))
    if tail in {"emit", "publish", "dispatch", "broadcast", "notify"} or ".emit" in low:
        out.append(("emits", name, {}))
    if tail in {"subscribe", "listen", "on", "add_listener", "add_event_listener"}:
        out.append(("subscribes", name, {}))
    if tail in {"send", "sendall", "produce", "enqueue", "put"} or any(x in low for x in ("kafka.", "queue.", "socket.")):
        out.append(("sends", name, {}))
    if tail in {"recv", "receive", "consume", "dequeue", "get"} and any(x in low for x in ("queue", "socket", "consumer", "message")):
        out.append(("receives", name, {}))
    if any(x in low for x in ("requests.get", "requests.post", "requests.put", "requests.delete", "httpx.", "urllib.request", "aiohttp.")):
        out.append(("network-request", name, {}))
    if any(x in low for x in ("cursor.execute", "connection.execute", ".query", ".executemany", "session.execute")):
        sql = _safe_unparse(args[0], 220) if args else ""
        out.append(("db-query", name, {"query": sql}))
    if low in {"open", "path.write_text", "path.write_bytes"} or tail in {"write_text", "write_bytes", "unlink", "rename", "replace"}:
        out.append(("filesystem-write", name, {}))
    if low.startswith("os.getenv") or low.startswith("os.environ") or tail == "getenv":
        out.append(("env-read", name, {}))
    return out


class _PythonEffectVisitor(ast.NodeVisitor):
    def __init__(self, path: str, symbols: list[dict], revision: str):
        self.path = path
        self.symbols = symbols
        self.revision = revision
        self.stack: list[tuple[str | None, int, int]] = []
        self.facts: list[dict] = []
        self._dedupe: set[tuple] = set()

    def _symbol_for_line(self, line: int) -> str | None:
        candidates = [s for s in self.symbols if int(s["start_line"]) <= line <= int(s["end_line"])]
        if not candidates:
            return None
        return min(candidates, key=lambda s: int(s["end_line"])-int(s["start_line"]))["id"]

    def _add(self, kind: str, target: str, node: ast.AST, *, trust: str = "parser", evidence: str | None = None, metadata: dict | None = None):
        if kind not in _EFFECT_KINDS or not target:
            return
        line = int(getattr(node, "lineno", 0) or 0) or None
        symbol_id = self._symbol_for_line(line or 1)
        key = (kind, target, line, symbol_id)
        if key in self._dedupe:
            return
        self._dedupe.add(key)
        self.facts.append({
            "id": stable_id("eff", self.path, str(line or 0), kind, target, symbol_id or ""),
            "path": self.path,
            "symbol_id": symbol_id,
            "kind": kind,
            "target": target[:240],
            "line": line,
            "trust": trust,
            "evidence": evidence or f"python-ast line {line or '?'}",
            "revision": self.revision,
            "metadata": metadata or {},
            "created_at": utc_now(),
        })

    def visit_Assign(self, node: ast.Assign):
        for target in node.targets:
            self._add("writes", _name(target), node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self._add("writes", _name(node.target), node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        self._add("mutates", _name(node.target), node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self._add("reads", node.id, node, trust="parser")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if isinstance(node.ctx, ast.Load):
            self._add("reads", _name(node), node, trust="parser")
        elif isinstance(node.ctx, ast.Store):
            self._add("writes", _name(node), node, trust="parser")
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return):
        self._add("returns", _safe_unparse(node.value) or "None", node)
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise):
        self._add("throws", _safe_unparse(node.exc) or "exception", node)
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await):
        self._add("awaits", _safe_unparse(node.value), node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        name = _name(node.func)
        for kind, target, meta in _classify_call(name, list(node.args)):
            self._add(kind, target, node, metadata=meta)
        self.generic_visit(node)


def _python_effects(path: str, text: str, symbols: list[dict], revision: str) -> tuple[list[dict], dict]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return [], {"provider": "python-ast-effects", "available": True, "parse_complete": False, "error": str(exc)}
    v = _PythonEffectVisitor(path, symbols, revision)
    v.visit(tree)
    return v.facts, {"provider": "python-ast-effects", "available": True, "parse_complete": True}


_JS_CALL_PATTERNS = [
    ("network-request", re.compile(r"\b(fetch|axios\.(?:get|post|put|delete|patch)|https?\.request)\s*\(")),
    ("emits", re.compile(r"\b(?:emit|dispatch|publish|broadcast)\s*\(")),
    ("subscribes", re.compile(r"\b(?:on|subscribe|addEventListener)\s*\(")),
    ("throws", re.compile(r"\bthrow\s+([^;]+)")),
    ("awaits", re.compile(r"\bawait\s+([^;]+)")),
    ("db-query", re.compile(r"\b(?:query|execute|findOne|findMany|aggregate)\s*\(")),
]


def _js_effects(path: str, text: str, symbols: list[dict], revision: str, language: str) -> tuple[list[dict], dict]:
    facts=[]; seen=set(); now=utc_now()
    def symbol_for(line: int):
        c=[s for s in symbols if int(s["start_line"])<=line<=int(s["end_line"])]
        return min(c,key=lambda s:int(s["end_line"])-int(s["start_line"]))["id"] if c else None
    for line_no, line in enumerate(text.splitlines(), 1):
        for kind, rx in _JS_CALL_PATTERNS:
            for m in rx.finditer(line):
                target=(m.group(1) if m.lastindex else m.group(0)).strip()[:240]
                key=(kind,target,line_no)
                if key in seen: continue
                seen.add(key); sid=symbol_for(line_no)
                facts.append({"id":stable_id("eff",path,str(line_no),kind,target,sid or ""),"path":path,"symbol_id":sid,
                              "kind":kind,"target":target,"line":line_no,"trust":"heuristic",
                              "evidence":f"{language}-effect-pattern line {line_no}","revision":revision,"metadata":{},"created_at":now})
    return facts,{"provider":f"{language}-effect-patterns","available":True,"parse_complete":False,
                  "claim_boundary":"Heuristic effect hints only; absence is not proof of no effect."}


def analyze_effect_text(path: str, text: str, symbols: list[dict], revision: str, language: str) -> tuple[list[dict], dict]:
    """Analyze one source text without persisting it. Used by counterfactual worlds and provider probes."""
    if language == "python":
        return _python_effects(path,text,symbols,revision)
    if language in {"javascript","typescript"}:
        return _js_effects(path,text,symbols,revision,language)
    return [], {"provider": "none", "available": False, "parse_complete": False, "reason": f"unsupported language: {language}"}


def compile_effects(root: Path, store, revision: str, paths: Iterable[str] | None = None) -> dict:
    wanted = list(paths) if paths is not None else [r["path"] for r in store.all_files()]
    compiled=0; total=0; providers=Counter(); skipped=0; failures=[]
    for rel in wanted:
        row=store.file_by_path(rel)
        if not row:
            store.delete_effect_facts_for_path(rel); continue
        lang=row["language"]
        if lang not in {"python","javascript","typescript"}:
            store.replace_effect_facts_for_path(rel, []); skipped+=1; continue
        path=root/rel
        try:
            text=path.read_text(encoding="utf-8",errors="replace")
        except OSError as exc:
            failures.append({"path":rel,"error":str(exc)}); continue
        symbols=[dict(x) for x in store.symbols_for_file(row["id"])]
        if lang=="python": facts,report=_python_effects(rel,text,symbols,revision)
        else: facts,report=_js_effects(rel,text,symbols,revision,lang)
        store.replace_effect_facts_for_path(rel,facts); compiled+=1; total+=len(facts); providers[report["provider"]]+=1
        if report.get("error"): failures.append({"path":rel,"error":report["error"]})
    return {"revision":revision,"paths_considered":len(wanted),"paths_compiled":compiled,"facts":total,"skipped":skipped,
            "providers":dict(providers),"failures":failures,
            "claim_boundary":"Effect Twin records static effect evidence. Parser/heuristic effects are possibilities, not observed runtime facts or complete data-flow proof."}


def effect_snapshot(store, revision: str, *, path: str | None = None, symbol_id: str | None = None, kind: str | None = None, limit: int = 1000, runtime_events=None) -> dict:
    rows=[]
    for r in store.effect_facts(path=path,symbol_id=symbol_id,kind=kind,limit=limit):
        d=dict(r)
        try:d["metadata"]=json.loads(d.pop("metadata_json") or "{}")
        except Exception:d["metadata"]={}; d.pop("metadata_json",None)
        d["runtime_support"]=correlate_runtime_fact(d,runtime_events or [],revision)
        rows.append(d)
    counts=Counter(r["kind"] for r in rows); support=Counter(r["runtime_support"]["grade"] for r in rows)
    return {"revision":revision,"effects":rows,"count":len(rows),"kind_counts":dict(counts),"runtime_support_counts":dict(support),
            "claim_boundary":"Static Effect Twin with revision-compatible runtime support annotations. Trust grades/provider evidence remain authoritative; runtime correlation is not causal proof and missing effects are not proof of absence."}

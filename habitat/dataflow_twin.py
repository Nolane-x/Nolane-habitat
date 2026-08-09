from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from .util import stable_id, utc_now
from .runtime_correlation import correlate_runtime_fact

_KINDS={"assigns","argument-to-call","call-result","return-flow","condition-flow","index-flow","attribute-flow"}


def _expr(node: ast.AST | None, limit: int = 180) -> str:
    if node is None: return ""
    try: text=ast.unparse(node)
    except Exception: text=node.__class__.__name__
    return " ".join(text.split())[:limit]


def _call_name(node: ast.AST | None) -> str:
    if isinstance(node,ast.Name): return node.id
    if isinstance(node,ast.Attribute):
        left=_call_name(node.value); return f"{left}.{node.attr}" if left else node.attr
    return _expr(node,120)


def _leaves(node: ast.AST | None) -> list[str]:
    if node is None: return []
    vals=[]
    class V(ast.NodeVisitor):
        def visit_Name(self,n):
            if isinstance(n.ctx,ast.Load): vals.append(n.id)
        def visit_Attribute(self,n):
            if isinstance(n.ctx,ast.Load): vals.append(_expr(n,140)); return
            self.generic_visit(n)
        def visit_Constant(self,n):
            if isinstance(n.value,(str,int,float,bool,type(None))): vals.append(repr(n.value)[:100])
    V().visit(node)
    out=[]; seen=set()
    for x in vals:
        if x and x not in seen: seen.add(x); out.append(x)
    return out[:24]


class _PythonFlow(ast.NodeVisitor):
    def __init__(self,path:str,symbols:list[dict],revision:str):
        self.path=path; self.symbols=symbols; self.revision=revision; self.facts=[]; self.seen=set()
    def _sid(self,line:int):
        c=[s for s in self.symbols if int(s["start_line"])<=line<=int(s["end_line"])]
        return min(c,key=lambda s:int(s["end_line"])-int(s["start_line"]))["id"] if c else None
    def add(self,kind,source,target,node,trust="parser",metadata=None):
        if kind not in _KINDS or not source or not target or source==target: return
        line=int(getattr(node,"lineno",0) or 0) or None; sid=self._sid(line or 1); key=(kind,source,target,line,sid)
        if key in self.seen:return
        self.seen.add(key); self.facts.append({"id":stable_id("flow",self.path,str(line or 0),kind,source,target,sid or ""),"path":self.path,"symbol_id":sid,
            "kind":kind,"source":source[:240],"target":target[:240],"line":line,"trust":trust,"evidence":f"python-ast flow line {line or '?'}","revision":self.revision,"metadata":metadata or {},"created_at":utc_now()})
    def _assignment(self,target,value,node):
        t=_expr(target,180)
        if isinstance(value,ast.Call):
            call=_call_name(value.func) or _expr(value.func,120)
            for arg in list(value.args)+[kw.value for kw in value.keywords]:
                for src in _leaves(arg): self.add("argument-to-call",src,call,node,metadata={"call":call})
            self.add("call-result",call,t,node,metadata={"call":call})
        for src in _leaves(value): self.add("assigns",src,t,node)
    def visit_Assign(self,node):
        for t in node.targets:self._assignment(t,node.value,node)
        self.generic_visit(node)
    def visit_AnnAssign(self,node):
        if node.value:self._assignment(node.target,node.value,node)
        self.generic_visit(node)
    def visit_AugAssign(self,node):
        t=_expr(node.target,180)
        for src in _leaves(node.value): self.add("assigns",src,t,node,metadata={"operator":node.op.__class__.__name__})
        self.generic_visit(node)
    def visit_Return(self,node):
        for src in _leaves(node.value): self.add("return-flow",src,"<return>",node)
        if isinstance(node.value,ast.Call): self.add("return-flow",_call_name(node.value.func),"<return>",node)
        self.generic_visit(node)
    def visit_If(self,node):
        for src in _leaves(node.test): self.add("condition-flow",src,"<branch>",node)
        self.generic_visit(node)
    def visit_While(self,node):
        for src in _leaves(node.test): self.add("condition-flow",src,"<loop-condition>",node)
        self.generic_visit(node)
    def visit_Call(self,node):
        call=_call_name(node.func) or _expr(node.func,120)
        for arg in list(node.args)+[kw.value for kw in node.keywords]:
            for src in _leaves(arg): self.add("argument-to-call",src,call,node,metadata={"call":call})
        self.generic_visit(node)


def _python(path,text,symbols,revision):
    try: tree=ast.parse(text,filename=path)
    except SyntaxError as exc:return [],{"provider":"python-ast-dataflow","parse_complete":False,"error":str(exc)}
    v=_PythonFlow(path,symbols,revision);v.visit(tree);return v.facts,{"provider":"python-ast-dataflow","parse_complete":True}

_JS_ASSIGN=re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;]+)")
_JS_CALL=re.compile(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(([^)]*)\)")
def _js(path,text,symbols,revision,language):
    facts=[];seen=set();now=utc_now()
    def sid(line):
        c=[s for s in symbols if int(s["start_line"])<=line<=int(s["end_line"])]
        return min(c,key=lambda s:int(s["end_line"])-int(s["start_line"]))["id"] if c else None
    def add(kind,src,tgt,line):
        if not src or not tgt or src==tgt:return
        key=(kind,src,tgt,line)
        if key in seen:return
        seen.add(key); si=sid(line);facts.append({"id":stable_id("flow",path,str(line),kind,src,tgt,si or ""),"path":path,"symbol_id":si,"kind":kind,"source":src[:240],"target":tgt[:240],"line":line,"trust":"heuristic","evidence":f"{language}-dataflow-pattern line {line}","revision":revision,"metadata":{},"created_at":now})
    for no,line in enumerate(text.splitlines(),1):
        m=_JS_ASSIGN.search(line)
        if m:
            target=m.group(1); rhs=m.group(2); cm=_JS_CALL.search(rhs)
            if cm:
                call=cm.group(1);add("call-result",call,target,no)
                for tok in re.findall(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*",cm.group(2)):add("argument-to-call",tok,call,no)
            for tok in re.findall(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*",rhs):
                if tok not in {target,"const","let","var"}:add("assigns",tok,target,no)
    return facts,{"provider":f"{language}-dataflow-patterns","parse_complete":False,"claim_boundary":"Heuristic hints only."}


def analyze_dataflow_text(path: str, text: str, symbols: list[dict], revision: str, language: str) -> tuple[list[dict], dict]:
    """Analyze one source text without persisting it. Counterfactual overlays use this to stay isolated."""
    if language == "python": return _python(path,text,symbols,revision)
    if language in {"javascript","typescript"}: return _js(path,text,symbols,revision,language)
    return [], {"provider":"none","parse_complete":False,"reason":f"unsupported language: {language}"}


def compile_dataflow(root:Path,store,revision:str,paths:Iterable[str]|None=None)->dict:
    wanted=list(paths) if paths is not None else [r["path"] for r in store.all_files()]
    compiled=0;total=0;skipped=0;providers=Counter();failures=[]
    for rel in wanted:
        row=store.file_by_path(rel)
        if not row:store.delete_dataflow_facts_for_path(rel);continue
        lang=row["language"]
        if lang not in {"python","javascript","typescript"}:store.replace_dataflow_facts_for_path(rel,[]);skipped+=1;continue
        try:text=(root/rel).read_text(encoding="utf-8",errors="replace")
        except OSError as exc:failures.append({"path":rel,"error":str(exc)});continue
        symbols=[dict(x) for x in store.symbols_for_file(row["id"])]
        facts,report=_python(rel,text,symbols,revision) if lang=="python" else _js(rel,text,symbols,revision,lang)
        store.replace_dataflow_facts_for_path(rel,facts);compiled+=1;total+=len(facts);providers[report["provider"]]+=1
        if report.get("error"):failures.append({"path":rel,"error":report["error"]})
    return {"revision":revision,"paths_considered":len(wanted),"paths_compiled":compiled,"facts":total,"skipped":skipped,"providers":dict(providers),"failures":failures,
      "claim_boundary":"Static intra-file dataflow evidence. It does not prove dynamic dispatch, aliases, interprocedural value identity, or runtime causality."}


def dataflow_snapshot(store,revision:str,*,path=None,symbol_id=None,kind=None,source=None,target=None,limit=1000,runtime_events=None)->dict:
    rows=[]
    for r in store.dataflow_facts(path=path,symbol_id=symbol_id,kind=kind,source=source,target=target,limit=limit):
        d=dict(r)
        try:d["metadata"]=json.loads(d.pop("metadata_json") or "{}")
        except Exception:d["metadata"]={};d.pop("metadata_json",None)
        rows.append(d)
    runtime_events=runtime_events or []
    for f in rows:
        f["runtime_support"]=correlate_runtime_fact(f,runtime_events,revision)
        f["observed_runtime_refs"]=[x.get("id") for x in f["runtime_support"]["runtime_refs"] if x.get("id")]
    support=Counter(r["runtime_support"]["grade"] for r in rows)
    return {"revision":revision,"flows":rows,"count":len(rows),"kind_counts":dict(Counter(r["kind"] for r in rows)),"runtime_support_counts":dict(support),
      "claim_boundary":"Static dataflow evidence with revision-compatible runtime support. Correlation is not dynamic value-flow identity or causal proof."}

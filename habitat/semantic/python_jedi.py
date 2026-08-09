from __future__ import annotations

import ast
import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
import threading

from ..compiler import CompiledFile
from ..model import OccurrenceRecord, RelationRecord
from ..util import stable_id

PROVIDER_ID = "python-jedi"
PROVIDER_SCHEMA = 3

_PROJECTS: "OrderedDict[str, object]" = OrderedDict()
_PROJECT_LOCK = threading.Lock()
_MAX_PROJECTS = 4

def _project_for(root: Path):
    """Return a bounded Jedi Project cache entry.

    The first alpha.7 experiment retained one Project per workspace indefinitely and made close() an
    accidental correctness/performance requirement. The admitted design is bounded LRU: callers do
    not need to close a workspace for global state to stay bounded, while repeated refreshes in a
    live workspace can still reuse provider setup.
    """
    import jedi  # type: ignore
    key=str(root.resolve())
    with _PROJECT_LOCK:
        for stale in [k for k in _PROJECTS if not Path(k).exists()]:
            _PROJECTS.pop(stale,None)
        value=_PROJECTS.get(key)
        if value is not None:
            _PROJECTS.move_to_end(key)
            return value, True
        value=jedi.Project(path=key,added_sys_path=[key])
        _PROJECTS[key]=value
        while len(_PROJECTS)>_MAX_PROJECTS:
            _PROJECTS.popitem(last=False)
        return value, False

def close_jedi_project(root: Path) -> None:
    with _PROJECT_LOCK:
        _PROJECTS.pop(str(root.resolve()),None)

def close_all_jedi_projects() -> None:
    with _PROJECT_LOCK:
        _PROJECTS.clear()

def jedi_project_status(root: Path) -> dict:
    key=str(root.resolve())
    with _PROJECT_LOCK:
        return {
            "running": key in _PROJECTS,
            "root": key,
            "persistent_session": key in _PROJECTS,
            "cache_policy": "bounded-lru",
            "cached_projects": len(_PROJECTS),
            "max_cached_projects": _MAX_PROJECTS,
            "close_required_for_boundedness": False,
        }



def probe() -> tuple[bool, str, str | None]:
    try:
        import jedi  # type: ignore
    except Exception as exc:
        return False, f"Jedi unavailable: {exc}", None
    return True, "Jedi static semantic engine available", getattr(jedi, "__version__", None)


def _python_domain_digest(compiled: list[CompiledFile]) -> str:
    rows = [(cf.file.path, cf.file.digest, cf.provider) for cf in compiled if cf.file.language == "python" and cf.file.parse_complete]
    return hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()


def _call_anchor(node: ast.AST) -> tuple[int, int, str] | None:
    if isinstance(node, ast.Name):
        return node.lineno, node.col_offset, node.id
    if isinstance(node, ast.Attribute):
        return node.lineno, max(node.col_offset, getattr(node, "end_col_offset", node.col_offset) - len(node.attr)), node.attr
    return None


def _caller_symbol(cf: CompiledFile, line: int):
    candidates = [s for s in cf.symbols if s.start_line <= line <= s.end_line and s.kind in {"function", "method"}]
    return min(candidates, key=lambda s: (s.end_line - s.start_line, -s.start_line), default=None)


def _symbol_lookup(compiled: list[CompiledFile]):
    by_path_line_name: dict[tuple[str, int, str], list] = {}
    by_path_name: dict[tuple[str, str], list] = {}
    root_paths = {cf.file.path: cf for cf in compiled}
    for cf in compiled:
        for sym in cf.symbols:
            by_path_line_name.setdefault((sym.path, sym.start_line, sym.name), []).append(sym)
            by_path_name.setdefault((sym.path, sym.name), []).append(sym)
    return root_paths, by_path_line_name, by_path_name


def _match_definition(root: Path, definition, by_path_line_name, by_path_name):
    module_path = getattr(definition, "module_path", None)
    if not module_path:
        return None
    try:
        p = Path(str(module_path)).resolve()
        rel = p.relative_to(root.resolve()).as_posix()
    except Exception:
        return None
    name = getattr(definition, "name", None)
    line = int(getattr(definition, "line", 0) or 0)
    if not name:
        return None
    exact = by_path_line_name.get((rel, line, name), [])
    if len(exact) == 1:
        return exact[0]
    same_name = by_path_name.get((rel, name), [])
    if len(same_name) == 1:
        return same_name[0]
    if same_name and line:
        return min(same_name, key=lambda s: abs(s.start_line - line))
    return None


def _python_api_surface_digest(compiled: list[CompiledFile]) -> str:
    """Conservative resolver surface shared by Jedi source partitions.

    Function bodies are intentionally excluded. Public/local definition identity and import topology are
    included because they can change what a call resolves to in another file. A surface change therefore
    invalidates all precision partitions; a body-only edit normally invalidates only its own source partition.
    """
    surface=[]
    for cf in compiled:
        if cf.file.language != "python" or not cf.file.parse_complete:
            continue
        symbols=[(x.name,x.qualified_name,x.kind,x.start_line) for x in cf.symbols]
        imports=[(src,target,kind,trust,evidence) for src,target,kind,trust,evidence in cf.unresolved_relations
                 if kind in {"imports_symbol","imports_module"}]
        surface.append((cf.file.path,sorted(symbols),sorted(imports)))
    raw=json.dumps(sorted(surface),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _compile_jedi_file(root: Path, cf: CompiledFile, project, by_path_line_name, by_path_name) -> tuple[list[RelationRecord],list[OccurrenceRecord],dict]:
    import jedi  # type: ignore
    path=root/cf.file.path
    relations=[]; occurrences=[]; unresolved=ambiguous=errors=calls_examined=0
    seen_rel=set()
    try:
        code=path.read_text(encoding="utf-8",errors="replace")
        tree=ast.parse(code,filename=cf.file.path)
        script=jedi.Script(code=code,path=str(path),project=project)
    except Exception:
        return [],[],{"calls_examined":0,"unresolved_calls":0,"ambiguous_calls":0,"file_errors":1}
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):
            continue
        anchor=_call_anchor(node.func)
        if not anchor:
            continue
        line,col,text=anchor
        caller=_caller_symbol(cf,line)
        if caller is None:
            continue
        calls_examined += 1
        try:
            definitions=script.goto(line,col,follow_imports=True,follow_builtin_imports=False)
        except Exception:
            errors += 1; continue
        targets=[]
        for d in definitions:
            sym=_match_definition(root,d,by_path_line_name,by_path_name)
            if sym is not None and sym.id != caller.id:
                targets.append(sym)
        uniq={x.id:x for x in targets}
        if len(uniq)!=1:
            ambiguous += int(len(uniq)>1); unresolved += int(len(uniq)==0); continue
        target=next(iter(uniq.values()))
        rkey=(caller.id,target.id,"calls",line)
        if rkey not in seen_rel:
            relations.append(RelationRecord(caller.id,target.id,"calls","semantic",
                                            f"line {line}; jedi-resolved call {cf.file.path}:{line}:{col + 1} -> {target.path}:{target.start_line}"))
            seen_rel.add(rkey)
        occurrences.append(OccurrenceRecord(
            stable_id("occ",cf.file.path,"jedi-call",str(line),str(col),target.id),
            cf.file.id,cf.file.path,"call",target.id,caller.id,text,line,col+1,line,col+1+len(text),
            PROVIDER_ID,"semantic",f"jedi goto -> {target.path}:{target.start_line}",
        ))
    return relations,occurrences,{"calls_examined":calls_examined,"unresolved_calls":unresolved,
                                  "ambiguous_calls":ambiguous,"file_errors":errors}


def compile_python_jedi(root: Path, compiled: list[CompiledFile], store) -> tuple[list[RelationRecord], list[OccurrenceRecord], dict]:
    """Resolve Python calls with per-source Jedi partitions and a conservative API-surface gate."""
    ok,reason,version=probe()
    py_files=[cf for cf in compiled if cf.file.language=="python" and cf.file.parse_complete]
    domain=_python_domain_digest(compiled)
    surface=_python_api_surface_digest(compiled)
    fp={"provider":PROVIDER_ID,"schema":PROVIDER_SCHEMA,"version":version,"available":ok}
    if not ok:
        return [],[],{"available":False,"reason":reason,"version":version,"files":len(py_files),"relations":0,"occurrences":0,
                     "cache_hit":False,"domain_digest":domain,"api_surface_digest":surface,"partitions_total":len(py_files),
                     "partitions_reused":0,"partitions_recomputed":0}

    project, project_reused = _project_for(root)
    _root_paths,by_path_line_name,by_path_name=_symbol_lookup(compiled)
    relations=[]; occurrences=[]; reused=recomputed=0
    aggregate={"calls_examined":0,"unresolved_calls":0,"ambiguous_calls":0,"file_errors":0}
    for cf in py_files:
        key=f"semantic-python-jedi-part-v2:{cf.file.id}"
        cached=store.load_project_cache(key)
        admitted=bool(cached and cached.get("source_digest")==cf.file.digest and cached.get("api_surface_digest")==surface and cached.get("fingerprint")==fp)
        if admitted:
            try:
                r=[RelationRecord(**x) for x in cached.get("relations",[])]
                o=[OccurrenceRecord(**x) for x in cached.get("occurrences",[])]
                metrics=dict(cached.get("metrics",{})); reused += 1
            except Exception:
                admitted=False
        if not admitted:
            r,o,metrics=_compile_jedi_file(root,cf,project,by_path_line_name,by_path_name); recomputed += 1
            store.save_project_cache(key,{"source_digest":cf.file.digest,"api_surface_digest":surface,"fingerprint":fp,
                                          "relations":[asdict(x) for x in r],"occurrences":[asdict(x) for x in o],"metrics":metrics})
        relations.extend(r); occurrences.extend(o)
        for k in aggregate:
            aggregate[k] += int(metrics.get(k,0))
    report={"available":True,"reason":reason,"version":version,"files":len(py_files),"relations":len(relations),
            "occurrences":len(occurrences),**aggregate,"cache_hit":bool(py_files and recomputed==0),"domain_digest":domain,
            "api_surface_digest":surface,"partitions_total":len(py_files),"partitions_reused":reused,"partitions_recomputed":recomputed,
            "project_session_reused":project_reused,"persistent_session":True,"project_cache_policy":"bounded-lru","trust_ceiling":"semantic","project_execution":False}
    store.save_project_cache("semantic-python-jedi-summary-v2",{"report":report,"fingerprint":fp,"api_surface_digest":surface})
    return relations,occurrences,report

def python_rename_sites(root: Path, symbol_row, new_name: str) -> dict:
    """Return exact Jedi-backed identifier spans for a safe project-wide Python rename.

    The result is a proposal only; mutation digest checks remain the commit authority. Columns are
    zero-based, matching Jedi. Aliased local names are intentionally not renamed when the original
    imported symbol keeps a distinct alias.
    """
    import keyword
    if not isinstance(new_name, str) or not new_name.isidentifier() or keyword.iskeyword(new_name):
        raise ValueError("new_name must be a non-keyword Python identifier")
    if symbol_row["language"] != "python":
        raise ValueError("python semantic rename requires a Python symbol")
    ok, reason, version = probe()
    if not ok:
        raise RuntimeError(reason)
    import jedi  # type: ignore
    path = (root / symbol_row["path"]).resolve()
    if not path.is_file():
        raise FileNotFoundError(symbol_row["path"])
    code = path.read_text(encoding="utf-8", errors="strict")
    project, _ = _project_for(root)
    script = jedi.Script(code=code, path=str(path), project=project)
    name = symbol_row["name"]
    anchors = [n for n in script.get_names(all_scopes=True, definitions=True, references=False)
               if n.name == name and int(n.line or 0) == int(symbol_row["start_line"])]
    if len(anchors) != 1:
        raise RuntimeError(f"semantic rename could not identify one exact definition anchor; found {len(anchors)}")
    anchor = anchors[0]
    refs = script.get_references(anchor.line, anchor.column, scope="project", include_builtins=False)
    sites=[]; outside=[]
    seen=set()
    root_resolved=root.resolve()
    for ref in refs:
        module_path=getattr(ref,"module_path",None)
        if not module_path or ref.name != name:
            continue
        rp=Path(str(module_path)).resolve()
        try:
            rel=rp.relative_to(root_resolved).as_posix()
        except Exception:
            outside.append(str(rp)); continue
        line=int(ref.line or 0); col=int(ref.column or 0)
        if line < 1 or col < 0:
            continue
        key=(rel,line,col)
        if key in seen: continue
        seen.add(key)
        sites.append({"path":rel,"start_line":line,"end_line":line,"start_column":col,"end_column":col+len(name),
                      "expected_text":name,"new_text":new_name,"is_definition":bool(ref.is_definition())})
    if not any(x["is_definition"] and x["path"]==symbol_row["path"] for x in sites):
        raise RuntimeError("semantic rename proposal lost the definition anchor")
    return {"provider":PROVIDER_ID,"provider_version":version,"trust":"semantic","symbol_id":symbol_row["id"],
            "old_name":name,"new_name":new_name,"sites":sorted(sites,key=lambda x:(x["path"],x["start_line"],x["start_column"])),
            "outside_project_references":outside,"site_count":len(sites),"project_execution":False}

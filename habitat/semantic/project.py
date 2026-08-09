from __future__ import annotations

import json
import os
import hashlib
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..compiler import (CompiledFile, build_relation_resolver_index, relation_partition_fingerprint, resolve_relations, resolve_relations_for_file)
from ..model import OccurrenceRecord, RelationRecord
from ..util import stable_id
from .typescript import _probe as _ts_probe, provider_version as _ts_provider_version
from .ts_language_service import get_typescript_session
from .python_jedi import compile_python_jedi, probe as _jedi_probe

PROJECT_SEMANTICS_VERSION = 8


@dataclass
class ProjectSemanticResult:
    relations: list[RelationRecord] = field(default_factory=list)
    occurrences: list[OccurrenceRecord] = field(default_factory=list)
    providers: dict = field(default_factory=dict)
    cache_hit: bool = False


def _evidence_line(evidence: str | None) -> int | None:
    if not evidence:
        return None
    m = re.search(r"\bline\s+(\d+)", evidence)
    return int(m.group(1)) if m else None


def _source_row(compiled: list[CompiledFile], object_id: str):
    for cf in compiled:
        if cf.file.id == object_id:
            return cf.file.path, cf.file.id, None
        for s in cf.symbols:
            if s.id == object_id:
                return s.path, s.file_id, s
    return None, None, None


def _definition_occurrences(compiled: list[CompiledFile]) -> list[OccurrenceRecord]:
    out: list[OccurrenceRecord] = []
    for cf in compiled:
        for s in cf.symbols:
            out.append(OccurrenceRecord(
                id=stable_id("occ", s.id, "definition", str(s.start_line)),
                file_id=s.file_id,
                path=s.path,
                role="definition",
                target_id=s.id,
                source_id=s.id,
                text=s.name,
                start_line=s.start_line,
                end_line=s.start_line,
                provider=cf.provider,
                trust=s.trust,
                evidence="symbol definition anchor",
            ))
    return out


def _relation_occurrences(compiled: list[CompiledFile], relations: list[RelationRecord]) -> list[OccurrenceRecord]:
    out: list[OccurrenceRecord] = []
    for r in relations:
        if r.kind not in {"calls", "imports", "imports_symbol", "tests"}:
            continue
        path, file_id, _ = _source_row(compiled, r.source_id)
        if not path or not file_id:
            continue
        line = _evidence_line(r.evidence) or 1
        role = "call" if r.kind == "calls" else "import" if r.kind.startswith("imports") else "test-link"
        out.append(OccurrenceRecord(
            id=stable_id("occ", path, role, r.source_id, r.target_id, str(line)),
            file_id=file_id,
            path=path,
            role=role,
            target_id=r.target_id,
            source_id=r.source_id,
            text=r.kind,
            start_line=line,
            end_line=line,
            provider="project-linker",
            trust=r.trust,
            evidence=r.evidence,
        ))
    return out


TS_PROJECT_SCRIPT = r'''
const fs = require('fs');
const path = require('path');
let ts;
try { ts = require('typescript'); }
catch (e) { if (process.env.NOLANE_TYPESCRIPT_PATH) ts = require(process.env.NOLANE_TYPESCRIPT_PATH); else throw e; }
const input = JSON.parse(fs.readFileSync(0,'utf8'));
const root = path.resolve(input.root);
const files = input.files.map(x => path.resolve(root,x));
const scanFiles = new Set((input.scan_files || input.files).map(x => path.normalize(path.resolve(root,x))));
let options = {allowJs:true, checkJs:false, noEmit:true, skipLibCheck:true, target:ts.ScriptTarget.ES2022,
               moduleResolution:ts.ModuleResolutionKind.NodeJs, module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.Preserve};
const configPath = ts.findConfigFile(root, ts.sys.fileExists, 'tsconfig.json') || ts.findConfigFile(root, ts.sys.fileExists, 'jsconfig.json');
if (configPath) {
  try {
    const cfg = ts.readConfigFile(configPath, ts.sys.readFile);
    const parsed = ts.parseJsonConfigFileContent(cfg.config, ts.sys, path.dirname(configPath));
    options = {...options, ...parsed.options, noEmit:true};
  } catch(e) {}
}
const host = ts.createCompilerHost(options, true);
const program = ts.createProgram(files, options, host);
const checker = program.getTypeChecker();
const allowed = new Set(files.map(f=>path.normalize(f)));
const out = {calls:[], imports:[], provider_version: ts.version};
function rel(f){ return path.relative(root,f).split(path.sep).join('/'); }
function pos(sf,node){ const lc=sf.getLineAndCharacterOfPosition(node.getStart(sf)); return {line:lc.line+1,column:lc.character+1}; }
function declaredName(node){
  if (node && node.name && node.name.getText) return node.name.getText();
  if (node && ts.isVariableDeclaration(node) && node.name) return node.name.getText();
  return null;
}
function container(node){
  let cur=node.parent;
  while(cur){
    if (ts.isFunctionDeclaration(cur)||ts.isMethodDeclaration(cur)||ts.isClassDeclaration(cur)||ts.isArrowFunction(cur)||ts.isFunctionExpression(cur)) {
      if ((ts.isArrowFunction(cur)||ts.isFunctionExpression(cur)) && cur.parent && ts.isVariableDeclaration(cur.parent)) cur=cur.parent;
      const n=declaredName(cur); if(n) return {name:n, ...pos(cur.getSourceFile(),cur)};
    }
    cur=cur.parent;
  }
  return null;
}
function targetFromSymbol(sym){
  if(!sym) return null;
  try { if (sym.flags & ts.SymbolFlags.Alias) sym=checker.getAliasedSymbol(sym); } catch(e) {}
  const decl=(sym.valueDeclaration || (sym.declarations && sym.declarations[0]));
  if(!decl) return null;
  const sf=decl.getSourceFile(); if(!sf || !allowed.has(path.normalize(sf.fileName))) return null;
  const p=pos(sf,decl); return {path:rel(sf.fileName), name:(sym.getName && sym.getName()) || declaredName(decl), line:p.line, column:p.column};
}
for(const sf of program.getSourceFiles()){
  if(!allowed.has(path.normalize(sf.fileName)) || !scanFiles.has(path.normalize(sf.fileName))) continue;
  function visit(node){
    if(ts.isImportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)){
      const spec=node.moduleSpecifier.text;
      const resolved=ts.resolveModuleName(spec,sf.fileName,options,host).resolvedModule;
      if(resolved && allowed.has(path.normalize(resolved.resolvedFileName))){
        const p=pos(sf,node); out.imports.push({source_path:rel(sf.fileName),target_path:rel(resolved.resolvedFileName),line:p.line,column:p.column,spec});
      }
    }
    if(ts.isCallExpression(node)){
      let lookup=node.expression;
      if(ts.isPropertyAccessExpression(node.expression)) lookup=node.expression.name;
      const target=targetFromSymbol(checker.getSymbolAtLocation(lookup));
      if(target){
        const p=pos(sf,node); out.calls.push({source_path:rel(sf.fileName),source_container:container(node),target,line:p.line,column:p.column,text:node.expression.getText(sf).slice(0,300)});
      }
    }
    ts.forEachChild(node,visit);
  }
  visit(sf);
}
process.stdout.write(JSON.stringify(out));
'''


def _match_symbol(compiled: list[CompiledFile], path: str, name: str | None, line: int | None):
    choices = []
    for cf in compiled:
        if cf.file.path != path:
            continue
        for s in cf.symbols:
            if name and s.name != name and s.qualified_name.split(".")[-1] != name:
                continue
            if line and not (s.start_line <= line <= s.end_line):
                # Definition start line from compiler can point inside declaration; retain nearby exact name as fallback.
                if abs(s.start_line - line) > 2:
                    continue
            choices.append(s)
    if len(choices) == 1:
        return choices[0]
    if line and choices:
        choices.sort(key=lambda s: (abs(s.start_line-line), s.end_line-s.start_line))
        if len(choices) == 1 or abs(choices[0].start_line-line) < abs(choices[1].start_line-line):
            return choices[0]
    return None


def _file_id(compiled: list[CompiledFile], path: str) -> str | None:
    for cf in compiled:
        if cf.file.path == path:
            return cf.file.id
    return None


def _typescript_project_semantics(root: Path, compiled: list[CompiledFile], scan_paths: set[str] | None = None) -> tuple[list[RelationRecord], list[OccurrenceRecord], dict]:
    ok, reason, _module_path = _ts_probe()
    ts_cfs = [cf for cf in compiled if cf.file.language in {"typescript","javascript"} and cf.file.parse_complete]
    ts_files = [cf.file.path for cf in ts_cfs]
    if not ok or not ts_files:
        return [], [], {"available": ok, "reason": reason if not ok else "no JS/TS files", "files": len(ts_files), "relations": 0}
    try:
        session=get_typescript_session(root)
        value=session.analyze(
            ts_files,
            [{"path":cf.file.path,"version":cf.file.digest} for cf in ts_cfs],
            sorted(scan_paths or set(ts_files)),
        )
    except Exception as exc:
        return [], [], {"available": False, "reason": f"persistent language-service provider failed: {exc}", "files": len(ts_files), "relations": 0, "persistent_session": False}

    relations: list[RelationRecord] = []
    occ: list[OccurrenceRecord] = []
    seen: set[tuple[str,str,str]] = set()
    for item in value.get("imports", []):
        sid=_file_id(compiled,item["source_path"]); tid=_file_id(compiled,item["target_path"])
        if not sid or not tid: continue
        key=(sid,tid,"imports")
        if key not in seen:
            seen.add(key); relations.append(RelationRecord(sid,tid,"imports","semantic",f"typescript-language-service line {item['line']} module {item.get('spec','')}"))
        occ.append(OccurrenceRecord(
            stable_id("occ",item["source_path"],"ts-import",str(item["line"]),item["target_path"]), sid,item["source_path"],"import",tid,sid,
            item.get("spec") or "import",int(item["line"]),int(item.get("column") or 0) or None,int(item["line"]),None,
            "typescript-language-service","semantic",f"resolved module to {item['target_path']}"
        ))
    for item in value.get("calls", []):
        target=item.get("target") or {}
        target_sym=_match_symbol(compiled,target.get("path",""),target.get("name"),target.get("line"))
        if not target_sym: continue
        source_id=_file_id(compiled,item["source_path"])
        container=item.get("source_container")
        if container:
            source_sym=_match_symbol(compiled,item["source_path"],container.get("name"),container.get("line"))
            if source_sym: source_id=source_sym.id
        if not source_id: continue
        key=(source_id,target_sym.id,"calls")
        if key not in seen:
            seen.add(key); relations.append(RelationRecord(source_id,target_sym.id,"calls","semantic",f"typescript-language-service line {item['line']}"))
        fid=_file_id(compiled,item["source_path"])
        if fid:
            occ.append(OccurrenceRecord(
                stable_id("occ",item["source_path"],"ts-call",str(item["line"]),target_sym.id), fid,item["source_path"],"call",target_sym.id,source_id,
                item.get("text") or target_sym.name,int(item["line"]),int(item.get("column") or 0) or None,int(item["line"]),None,
                "typescript-language-service","semantic",f"compiler-resolved declaration {target_sym.path}:{target_sym.start_line}"
            ))
    report={
        "available":True,"reason":"persistent TypeScript LanguageService + TypeChecker","version":value.get("provider_version"),
        "files":len(ts_files),"scanned_files":len(scan_paths or set(ts_files)),"relations":len(relations),"occurrences":len(occ),
        "persistent_session":True,"session_id":value.get("session_id"),"session_reused":bool(value.get("session_reused")),
        "request_count":int(value.get("request_count") or 0),"hydrated_files":int(value.get("hydrated_files") or 0),
        "removed_files":int(value.get("removed_files") or 0),"file_set_changed":bool(value.get("file_set_changed")),
    }
    return relations,occ,report


def _provider_fingerprint() -> dict:
    return {
        "project_semantics_version": PROJECT_SEMANTICS_VERSION,
        "typescript_version": _ts_provider_version(),
        "python_jedi_version": _jedi_probe()[2],
    }


def _semantic_domain_digest(compiled: list[CompiledFile], languages: set[str] | None = None) -> str:
    """Digest only files that can influence a semantic provider domain.

    A README edit must not invalidate TypeScript or Python project linking.  The digest includes
    provider identity as well as source digest so parser/provider migrations cannot silently reuse
    semantically incompatible cache artifacts.
    """
    rows=[]
    for cf in compiled:
        if languages is not None and cf.file.language not in languages:
            continue
        if languages is None and not (cf.symbols or cf.unresolved_relations or cf.file.language in {"python","javascript","typescript","java","html","css"}):
            continue
        rows.append((cf.file.path,cf.file.digest,cf.file.language,cf.provider,cf.file.parse_complete))
    payload=json.dumps(sorted(rows),separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_relation_cache(store, key: str, domain_digest: str, fingerprint: dict) -> list[RelationRecord] | None:
    cached=store.load_project_cache(key)
    if not cached:
        return None
    if cached.get("version") != PROJECT_SEMANTICS_VERSION or cached.get("domain_digest") != domain_digest or cached.get("fingerprint") != fingerprint:
        return None
    try:
        return [RelationRecord(**x) for x in cached.get("relations",[])]
    except Exception:
        return None


def _base_relations_cached(compiled: list[CompiledFile], store) -> tuple[list[RelationRecord], dict]:
    """Resolve project relations through dependency-bound source partitions.

    Alpha.3 cached the entire built-in resolver domain. Alpha.4 keeps one partition per source file.
    Each partition fingerprint contains the source parser facts plus only the target candidate sets those
    facts can observe. Body-only edits therefore avoid recomputing unrelated callers, while exported-name
    changes invalidate the exact reverse dependency closure that can see the changed resolution surface.
    """
    index = build_relation_resolver_index(compiled)
    prefix = "semantic-base-partition-v7:"
    active_keys: set[str] = set()
    relations: list[RelationRecord] = []
    reused = recomputed = 0
    dirty_paths: list[str] = []
    partition_reports: list[dict] = []

    partition_sources = [cf for cf in compiled if cf.unresolved_relations]
    for cf in partition_sources:
        key = prefix + cf.file.id
        active_keys.add(key)
        fingerprint = relation_partition_fingerprint(cf, index)
        cached = store.load_project_cache(key)
        part: list[RelationRecord] | None = None
        if cached and cached.get("version") == PROJECT_SEMANTICS_VERSION and cached.get("fingerprint") == fingerprint:
            try:
                part = [RelationRecord(**x) for x in cached.get("relations", [])]
            except Exception:
                part = None
        if part is None:
            part = resolve_relations_for_file(cf, index)
            store.save_project_cache(key, {
                "version": PROJECT_SEMANTICS_VERSION,
                "fingerprint": fingerprint,
                "path": cf.file.path,
                "source_digest": cf.file.digest,
                "relations": [asdict(x) for x in part],
            })
            recomputed += 1; dirty_paths.append(cf.file.path)
            cache_hit = False
        else:
            reused += 1; cache_hit = True
        relations.extend(part)
        partition_reports.append({"path": cf.file.path, "cache_hit": cache_hit, "relations": len(part)})

    stale = [k for k in store.project_cache_keys(prefix) if k not in active_keys]
    for key in stale:
        store.delete_project_cache(key)

    # A compatibility domain digest remains useful for reports and old probes, but no longer decides
    # partition admission. It is intentionally not used as a cache gate.
    domain = _semantic_domain_digest(compiled)
    return relations, {
        "cache_hit": recomputed == 0,
        "domain_digest": domain,
        "relations": len(relations),
        "partitioned": True,
        "partitions_total": len(partition_sources),
        "partitions_reused": reused,
        "partitions_recomputed": recomputed,
        "stale_partitions_removed": len(stale),
        "dirty_paths": dirty_paths,
        "partition_sample": partition_reports[:40],
    }

def _typescript_api_surface_digest(compiled: list[CompiledFile]) -> str:
    rows=[]
    for cf in compiled:
        if cf.file.language not in {"typescript","javascript"} or not cf.file.parse_complete:
            continue
        symbols=[(x.name,x.qualified_name,x.kind,x.start_line) for x in cf.symbols]
        imports=[(src,target,kind,trust,evidence) for src,target,kind,trust,evidence in cf.unresolved_relations
                 if kind in {"imports_symbol","imports_module"}]
        rows.append((cf.file.path,sorted(symbols),sorted(imports)))
    return hashlib.sha256(json.dumps(sorted(rows),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _typescript_relations_cached(root: Path, compiled: list[CompiledFile], store) -> tuple[list[RelationRecord],list[OccurrenceRecord],dict]:
    ts_cfs=[cf for cf in compiled if cf.file.language in {"typescript","javascript"} and cf.file.parse_complete]
    ts_files=[cf.file.path for cf in ts_cfs]
    if not ts_files:
        return [],[],{"available":True,"reason":"no JS/TS files","files":0,"relations":0,"occurrences":0,"cache_hit":True,
                     "partitions_total":0,"partitions_reused":0,"partitions_recomputed":0,"program_invoked":False}
    version=_ts_provider_version(); ok,reason,module_path=_ts_probe()
    domain=_semantic_domain_digest(compiled,{"typescript","javascript"})
    surface=_typescript_api_surface_digest(compiled)
    fp={"project_semantics_version":PROJECT_SEMANTICS_VERSION,"typescript_version":version,"available":ok}
    if not ok:
        return [],[],{"available":False,"reason":reason,"version":version,"files":len(ts_files),"relations":0,"occurrences":0,"cache_hit":False,
                     "domain_digest":domain,"api_surface_digest":surface,"partitions_total":len(ts_files),"partitions_reused":0,
                     "partitions_recomputed":0,"program_invoked":False}

    reused_parts={}; dirty=[]
    for cf in ts_cfs:
        key=f"semantic-typescript-part-v8:{cf.file.id}"
        cached=store.load_project_cache(key)
        if cached and cached.get("source_digest")==cf.file.digest and cached.get("api_surface_digest")==surface and cached.get("fingerprint")==fp:
            try:
                reused_parts[cf.file.path]=([RelationRecord(**x) for x in cached.get("relations",[])],
                                            [OccurrenceRecord(**x) for x in cached.get("occurrences",[])])
                continue
            except Exception:
                pass
        dirty.append(cf)

    computed_by_path={p:([],[]) for p in [cf.file.path for cf in dirty]}
    provider_report={"available":True,"reason":"TypeScript Program + TypeChecker","version":version,"files":len(ts_files),"relations":0,"occurrences":0}
    if dirty:
        new_rel,new_occ,provider_report=_typescript_project_semantics(root,compiled,{cf.file.path for cf in dirty})
        for r in new_rel:
            path,_,_=_source_row(compiled,r.source_id)
            if path in computed_by_path: computed_by_path[path][0].append(r)
        for o in new_occ:
            if o.path in computed_by_path: computed_by_path[o.path][1].append(o)
        for cf in dirty:
            r,o=computed_by_path[cf.file.path]
            store.save_project_cache(f"semantic-typescript-part-v8:{cf.file.id}",{
                "source_digest":cf.file.digest,"api_surface_digest":surface,"fingerprint":fp,
                "relations":[asdict(x) for x in r],"occurrences":[asdict(x) for x in o],
            })

    relations=[]; occ=[]
    for cf in ts_cfs:
        r,o=(computed_by_path.get(cf.file.path) if cf.file.path in computed_by_path else reused_parts.get(cf.file.path,([],[])))
        relations.extend(r); occ.extend(o)
    report=dict(provider_report)
    report.update({"available":True,"reason":provider_report.get("reason","TypeScript Program + TypeChecker"),"version":provider_report.get("version") or version,
                   "files":len(ts_files),"relations":len(relations),"occurrences":len(occ),"cache_hit":not dirty,"domain_digest":domain,
                   "api_surface_digest":surface,"partitions_total":len(ts_files),"partitions_reused":len(reused_parts),
                   "partitions_recomputed":len(dirty),"program_invoked":bool(dirty),"scanned_files":len(dirty)})
    store.save_project_cache("semantic-typescript-summary-v8",{"report":report,"fingerprint":fp,"api_surface_digest":surface})
    return relations,occ,report


def compile_project_semantics(root: Path, compiled: list[CompiledFile], store, root_digest: str, changed: bool) -> ProjectSemanticResult:
    """Compile semantic graph using provider-domain caches rather than one root-wide cache.

    `changed` remains in the call contract for alpha.2 compatibility, but cache admission is based on
    provider-domain digests.  A documentation-only edit therefore does not rerun TypeScript or the
    project relation resolver, while a JS/TS edit invalidates only the affected provider domain.
    """
    base,base_report=_base_relations_cached(compiled,store)
    py_rel,py_occ,py_report=compile_python_jedi(root,compiled,store)
    ts_rel,ts_occ,ts_report=_typescript_relations_cached(root,compiled,store)

    # Precise provider overlays replace weaker call edges at the same source call site.  We still keep
    # exact containment/import facts from the builtin compiler because Jedi/TypeScript overlays focus on
    # reference resolution rather than structural ownership.
    precise = [*py_rel, *ts_rel]
    # A precise provider may resolve one call site while another call in the same function remains
    # unresolved. Supersede only parser/heuristic edges anchored at the exact proven call-site line.
    precise_call_sites={(r.source_id,_evidence_line(r.evidence)) for r in precise if r.kind=="calls" and r.trust=="semantic" and _evidence_line(r.evidence)}
    filtered_base=[r for r in base if not (
        r.kind=="calls" and r.trust in {"heuristic","parser"} and
        (r.source_id,_evidence_line(r.evidence)) in precise_call_sites
    )]
    merged={(r.source_id,r.target_id,r.kind):r for r in filtered_base}
    for r in precise:
        merged[(r.source_id,r.target_id,r.kind)]=r
    merged_relations=list(merged.values())

    occurrences=_definition_occurrences(compiled)+_relation_occurrences(compiled,merged_relations)+py_occ+ts_occ
    occ_map={}
    rank={"exact":5,"semantic":4,"parser":3,"derived":2,"heuristic":1}
    provider_rank={"python-jedi":4,"typescript-program":4,"project-linker":2}
    for o in occurrences:
        key=(o.path,o.role,o.target_id,o.source_id,o.start_line)
        prev=occ_map.get(key)
        current_rank=(rank.get(o.trust,0), provider_rank.get(o.provider,1), int(o.start_column is not None))
        previous_rank=(rank.get(prev.trust,0), provider_rank.get(prev.provider,1), int(prev.start_column is not None)) if prev else (-1,-1,-1)
        if prev is None or current_rank>previous_rank:
            occ_map[key]=o
    compat_fp=_provider_fingerprint()
    compat=store.load_project_cache("semantic-project-v2")
    compat_drift=bool(compat and compat.get("provider_fingerprint") != compat_fp)
    full_hit=bool((not changed) and base_report.get("cache_hit") and py_report.get("cache_hit") and ts_report.get("cache_hit") and not compat_drift)
    providers={
        "base-resolver":base_report,
        "python-jedi":py_report,
        "typescript-project":ts_report,
        "cache":{
            "reused":full_hit,
            "provider_domain_reuse":{
                "base":bool(base_report.get("cache_hit")),
                "python_jedi":bool(py_report.get("cache_hit")),
                "typescript":bool(ts_report.get("cache_hit")),
            },
            "compatibility_gate_drift":compat_drift,
        },
    }
    # Keep the alpha.2 cache identity as a compatibility/admission sentinel.  Alpha.3 provider-domain
    # caches carry the actual heavy artifacts, while this record lets old workspaces and probes force
    # one conservative miss when provider identity drifts.
    store.save_project_cache("semantic-project-v2",{
        "version":PROJECT_SEMANTICS_VERSION,"root_digest":root_digest,"provider_fingerprint":compat_fp,
        "providers":providers,
    })
    return ProjectSemanticResult(merged_relations,list(occ_map.values()),providers,full_hit)


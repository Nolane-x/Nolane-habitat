from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .toml_compat import tomllib

from .util import stable_id


def _node(kind: str, name: str, *, path: str | None = None, trust: str = "parser", metadata: dict | None = None) -> dict:
    return {"id": stable_id("world", kind, name, path or ""), "type": kind, "label": name, "path": path,
            "trust": trust, "metadata": metadata or {}}


def _edge(source: str, target: str, kind: str, trust: str = "parser", evidence: str | None = None) -> dict:
    return {"source": source, "target": target, "kind": kind, "trust": trust, "evidence": evidence}


def _load_text(path: Path, limit: int = 2_000_000) -> str:
    data=path.read_bytes()[:limit]
    return data.decode("utf-8", errors="replace")


def _dockerfile(rel: str, text: str):
    nodes=[]; edges=[]; root=_node("build", rel, path=rel); nodes.append(root)
    for line_no,line in enumerate(text.splitlines(),1):
        m=re.match(r"\s*FROM\s+([^\s]+)",line,re.I)
        if m:
            image=_node("container-image",m.group(1),path=rel); nodes.append(image); edges.append(_edge(root["id"],image["id"],"builds-from","parser",f"Dockerfile line {line_no}"))
        m=re.match(r"\s*EXPOSE\s+(.+)",line,re.I)
        if m:
            for port in m.group(1).split():
                p=_node("port",port,path=rel); nodes.append(p); edges.append(_edge(root["id"],p["id"],"exposes","parser",f"Dockerfile line {line_no}"))
    return nodes,edges


def _compose(rel: str, text: str):
    nodes=[];edges=[]; services={}; current=None; in_services=False; in_depends=False
    for line_no,line in enumerate(text.splitlines(),1):
        if re.match(r"^services:\s*$",line): in_services=True; current=None; continue
        if in_services:
            m=re.match(r"^  ([A-Za-z0-9_.-]+):\s*$",line)
            if m:
                current=m.group(1); in_depends=False
                n=_node("service",current,path=rel,trust="heuristic",metadata={"source":"compose"});services[current]=n;nodes.append(n);continue
            if current and re.match(r"^    depends_on:\s*$",line): in_depends=True;continue
            if current and in_depends:
                dm=re.match(r"^      -\s*([A-Za-z0-9_.-]+)",line) or re.match(r"^      ([A-Za-z0-9_.-]+):",line)
                if dm:
                    dep=dm.group(1)
                    if dep not in services:
                        services[dep]=_node("service",dep,path=rel,trust="heuristic",metadata={"source":"compose"});nodes.append(services[dep])
                    edges.append(_edge(services[current]["id"],services[dep]["id"],"depends-on","heuristic",f"compose line {line_no}"));continue
            if line and not line.startswith(" "): in_services=False; current=None; in_depends=False
    return nodes,edges


def _github_workflow(rel: str, text: str):
    nodes=[];edges=[]; workflow=_node("ci-workflow",Path(rel).name,path=rel,trust="heuristic");nodes.append(workflow); in_jobs=False
    jobs={}
    for line_no,line in enumerate(text.splitlines(),1):
        if re.match(r"^jobs:\s*$",line): in_jobs=True;continue
        if in_jobs:
            m=re.match(r"^  ([A-Za-z0-9_.-]+):\s*$",line)
            if m:
                name=m.group(1); n=_node("ci-job",name,path=rel,trust="heuristic");jobs[name]=n;nodes.append(n);edges.append(_edge(workflow["id"],n["id"],"contains","heuristic",f"workflow line {line_no}"));continue
            if line and not line.startswith(" "): in_jobs=False
    return nodes,edges


def _openapi(rel: str, text: str):
    nodes=[];edges=[]; api=_node("api-spec",Path(rel).name,path=rel);nodes.append(api)
    try:
        data=json.loads(text) if rel.endswith(".json") else None
    except Exception:data=None
    if isinstance(data,dict) and isinstance(data.get("paths"),dict):
        for p,ops in list(data["paths"].items())[:500]:
            ep=_node("api-route",p,path=rel);nodes.append(ep);edges.append(_edge(api["id"],ep["id"],"declares","parser","OpenAPI paths"))
            if isinstance(ops,dict):
                for method in ops:
                    if method.lower() in {"get","post","put","patch","delete","options","head"}:
                        op=_node("api-operation",f"{method.upper()} {p}",path=rel);nodes.append(op);edges.append(_edge(ep["id"],op["id"],"operation","parser","OpenAPI operation"))
    else:
        in_paths=False
        for line_no,line in enumerate(text.splitlines(),1):
            if re.match(r"^paths:\s*$",line): in_paths=True;continue
            if in_paths:
                m=re.match(r"^  (/[^:]+):\s*$",line)
                if m:
                    p=m.group(1);ep=_node("api-route",p,path=rel,trust="heuristic");nodes.append(ep);edges.append(_edge(api["id"],ep["id"],"declares","heuristic",f"OpenAPI line {line_no}"))
                elif line and not line.startswith(" "): in_paths=False
    return nodes,edges


def _sql(rel: str, text: str):
    nodes=[];edges=[]; migration=_node("db-migration",Path(rel).name,path=rel,trust="heuristic");nodes.append(migration)
    for m in re.finditer(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?([A-Za-z_][\w.$-]*)",text,re.I):
        t=_node("db-table",m.group(1),path=rel,trust="heuristic");nodes.append(t);edges.append(_edge(migration["id"],t["id"],"creates","heuristic","SQL CREATE TABLE"))
    for m in re.finditer(r"\bALTER\s+TABLE\s+[\"`\[]?([A-Za-z_][\w.$-]*)",text,re.I):
        t=_node("db-table",m.group(1),path=rel,trust="heuristic");nodes.append(t);edges.append(_edge(migration["id"],t["id"],"alters","heuristic","SQL ALTER TABLE"))
    return nodes,edges


def _package_json(rel: str, text: str):
    nodes=[];edges=[]
    try:data=json.loads(text)
    except Exception:return nodes,edges
    pkg=_node("package",data.get("name") or Path(rel).parent.name or "package",path=rel);nodes.append(pkg)
    for name,cmd in list((data.get("scripts") or {}).items())[:100]:
        s=_node("build-task",name,path=rel,metadata={"command":str(cmd)[:300]});nodes.append(s);edges.append(_edge(pkg["id"],s["id"],"exposes-task","parser","package.json scripts"))
    return nodes,edges


def _pyproject(rel: str, data: dict):
    nodes=[];edges=[]; project=data.get("project") or {}; name=project.get("name") or "python-project"
    pkg=_node("package",name,path=rel);nodes.append(pkg)
    scripts=project.get("scripts") or {}
    for n,target in list(scripts.items())[:100]:
        t=_node("build-task",n,path=rel,metadata={"target":str(target)});nodes.append(t);edges.append(_edge(pkg["id"],t["id"],"exposes-task","parser","pyproject scripts"))
    return nodes,edges


def _kubernetes(rel: str, text: str):
    nodes=[];edges=[]
    docs=re.split(r"^---\s*$",text,flags=re.M)
    for i,doc in enumerate(docs[:200]):
        km=re.search(r"^kind:\s*([^#\n]+)",doc,re.M); nm=re.search(r"^\s{0,4}name:\s*([^#\n]+)",doc,re.M)
        if not km or not nm: continue
        kind=km.group(1).strip(); name=nm.group(1).strip(); n=_node("infra-resource",f"{kind}/{name}",path=rel,trust="heuristic",metadata={"kind":kind});nodes.append(n)
        for dep in re.findall(r"(?:serviceName|secretName|configMapRef:\s*\n\s*name):\s*([A-Za-z0-9_.-]+)",doc):
            d=_node("infra-resource",dep,path=rel,trust="heuristic");nodes.append(d);edges.append(_edge(n["id"],d["id"],"references","heuristic",f"k8s document {i+1}"))
    return nodes,edges


def build_project_world(root: Path, store_or_rows, *, max_files: int = 1000) -> dict:
    nodes=[]; edges=[]; providers={}; examined=0
    rows=store_or_rows.all_files() if hasattr(store_or_rows,"all_files") else list(store_or_rows)
    for row in rows[:max_files]:
        rel=row["path"]; name=Path(rel).name; lower=rel.casefold(); path=root/rel
        try:
            if name=="pyproject.toml":
                data=tomllib.loads(_load_text(path)); ns,es=_pyproject(rel,data);provider="pyproject"
            elif name=="package.json": ns,es=_package_json(rel,_load_text(path));provider="package-json"
            elif name.casefold()=="dockerfile" or name.startswith("Dockerfile."):
                ns,es=_dockerfile(rel,_load_text(path));provider="dockerfile"
            elif name in {"docker-compose.yml","docker-compose.yaml","compose.yml","compose.yaml"}:
                ns,es=_compose(rel,_load_text(path));provider="compose-heuristic"
            elif lower.startswith(".github/workflows/") and Path(rel).suffix.casefold() in {".yml",".yaml"}:
                ns,es=_github_workflow(rel,_load_text(path));provider="github-workflow-heuristic"
            elif "openapi" in lower or "swagger" in lower:
                ns,es=_openapi(rel,_load_text(path));provider="openapi"
            elif Path(rel).suffix.casefold()==".sql": ns,es=_sql(rel,_load_text(path));provider="sql-heuristic"
            elif Path(rel).suffix.casefold() in {".yml",".yaml"}:
                text=_load_text(path)
                if re.search(r"^apiVersion:\s*",text,re.M) and re.search(r"^kind:\s*",text,re.M): ns,es=_kubernetes(rel,text);provider="kubernetes-heuristic"
                else: continue
            else: continue
        except Exception:
            continue
        examined+=1; nodes.extend(ns);edges.extend(es);providers[provider]=providers.get(provider,0)+1
    # de-duplicate while preserving strongest metadata encountered
    nmap={}
    for n in nodes:
        nmap.setdefault(n["id"],n)
    dedges=[];seen=set()
    for e in edges:
        k=(e["source"],e["target"],e["kind"])
        if k not in seen and e["source"] in nmap and e["target"] in nmap:
            seen.add(k);dedges.append(e)
    return {"nodes":list(nmap.values()),"edges":dedges,"providers":providers,"files_examined":examined,
            "claim_boundary":"Project World parses selected repository manifests/configuration into bounded typed entities. Heuristic YAML/SQL relations are orientation evidence, not complete deployment/runtime truth."}

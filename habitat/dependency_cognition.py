from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib=None


def _item(ecosystem: str, name: str, spec: str | None, source: str, scope: str="runtime") -> dict[str,Any]:
    return {"ecosystem":ecosystem,"name":name,"specifier":spec,"source":source,"scope":scope,"resolved":False}


def snapshot(root: Path) -> dict[str,Any]:
    root=root.resolve(); deps=[]; manifests=[]; lockfiles=[]; parse_errors=[]
    pyproject=root/"pyproject.toml"
    if pyproject.is_file() and tomllib:
        manifests.append("pyproject.toml")
        try:
            data=tomllib.loads(pyproject.read_text(encoding="utf-8"))
            for raw in ((data.get("project") or {}).get("dependencies") or []):
                m=re.match(r"\s*([A-Za-z0-9_.-]+)(.*)",str(raw));
                if m: deps.append(_item("python",m.group(1),m.group(2).strip() or None,"pyproject.toml"))
            for group,vals in (((data.get("project") or {}).get("optional-dependencies") or {}).items()):
                for raw in vals:
                    m=re.match(r"\s*([A-Za-z0-9_.-]+)(.*)",str(raw));
                    if m: deps.append(_item("python",m.group(1),m.group(2).strip() or None,"pyproject.toml",f"optional:{group}"))
        except Exception as exc: parse_errors.append({"path":"pyproject.toml","error":str(exc)})
    req=root/"requirements.txt"
    if req.is_file():
        manifests.append("requirements.txt")
        for line in req.read_text(encoding="utf-8",errors="replace").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or line.startswith("-"): continue
            m=re.match(r"([A-Za-z0-9_.-]+)(.*)",line)
            if m: deps.append(_item("python",m.group(1),m.group(2).strip() or None,"requirements.txt"))
    pkg=root/"package.json"
    if pkg.is_file():
        manifests.append("package.json")
        try:
            data=json.loads(pkg.read_text(encoding="utf-8"))
            for section,scope in (("dependencies","runtime"),("devDependencies","dev"),("peerDependencies","peer"),("optionalDependencies","optional")):
                for name,spec in (data.get(section) or {}).items(): deps.append(_item("npm",name,str(spec),"package.json",scope))
        except Exception as exc: parse_errors.append({"path":"package.json","error":str(exc)})
    pom=root/"pom.xml"
    if pom.is_file():
        manifests.append("pom.xml")
        text=pom.read_text(encoding="utf-8",errors="replace")
        for block in re.findall(r"<dependency>(.*?)</dependency>",text,flags=re.S):
            aid=re.search(r"<artifactId>(.*?)</artifactId>",block); gid=re.search(r"<groupId>(.*?)</groupId>",block); ver=re.search(r"<version>(.*?)</version>",block)
            if aid: deps.append(_item("maven",((gid.group(1)+":") if gid else "")+aid.group(1),ver.group(1) if ver else None,"pom.xml"))
    for name in ("package-lock.json","pnpm-lock.yaml","yarn.lock","uv.lock","poetry.lock","Pipfile.lock","Cargo.lock","go.sum","gradle.lockfile"):
        if (root/name).is_file(): lockfiles.append(name)
    unique={}
    for d in deps: unique[(d["ecosystem"],d["name"],d["source"],d["scope"])]=d
    values=sorted(unique.values(),key=lambda x:(x["ecosystem"],x["name"],x["source"],x["scope"]))
    return {"manifests":sorted(manifests),"lockfiles":sorted(lockfiles),"direct_dependencies":values,"count":len(values),"parse_errors":parse_errors,
            "claim_boundary":"Direct manifest cognition only. Transitive resolution, vulnerability status, external API compatibility and lockfile semantic resolution are not inferred."}


def query(root: Path, term: str) -> dict:
    if not isinstance(term,str) or not term.strip(): raise ValueError("term must be non-empty")
    snap=snapshot(root); q=term.casefold(); matches=[d for d in snap["direct_dependencies"] if q in d["name"].casefold() or q in (d.get("specifier") or "").casefold()]
    return {"query":term,"matches":matches,"count":len(matches),"manifests":snap["manifests"],"lockfiles":snap["lockfiles"],"claim_boundary":snap["claim_boundary"]}


def _norm_name(ecosystem: str, name: str) -> str:
    return name.casefold().replace("_","-") if ecosystem=="python" else name.casefold()


def lock_snapshot(root: Path) -> dict[str,Any]:
    root=root.resolve(); locked=[]; parse_errors=[]
    package_lock=root/"package-lock.json"
    if package_lock.is_file():
        try:
            data=json.loads(package_lock.read_text(encoding="utf-8"))
            packages=data.get("packages") or {}
            for key,val in packages.items():
                if not key.startswith("node_modules/"): continue
                name=key[len("node_modules/"):]
                version=(val or {}).get("version")
                if version: locked.append({"ecosystem":"npm","name":name,"version":str(version),"source":"package-lock.json"})
            if not packages:
                for name,val in (data.get("dependencies") or {}).items():
                    if isinstance(val,dict) and val.get("version"): locked.append({"ecosystem":"npm","name":name,"version":str(val["version"]),"source":"package-lock.json"})
        except Exception as exc: parse_errors.append({"path":"package-lock.json","error":str(exc)})
    poetry=root/"poetry.lock"
    if poetry.is_file() and tomllib:
        try:
            data=tomllib.loads(poetry.read_text(encoding="utf-8"))
            for pkg in data.get("package") or []:
                if pkg.get("name") and pkg.get("version"): locked.append({"ecosystem":"python","name":str(pkg["name"]),"version":str(pkg["version"]),"source":"poetry.lock"})
        except Exception as exc: parse_errors.append({"path":"poetry.lock","error":str(exc)})
    uv=root/"uv.lock"
    if uv.is_file() and tomllib:
        try:
            data=tomllib.loads(uv.read_text(encoding="utf-8"))
            for pkg in data.get("package") or []:
                if pkg.get("name") and pkg.get("version"): locked.append({"ecosystem":"python","name":str(pkg["name"]),"version":str(pkg["version"]),"source":"uv.lock"})
        except Exception as exc: parse_errors.append({"path":"uv.lock","error":str(exc)})
    pipfile=root/"Pipfile.lock"
    if pipfile.is_file():
        try:
            data=json.loads(pipfile.read_text(encoding="utf-8"))
            for section,scope in (("default","runtime"),("develop","dev")):
                for name,val in (data.get(section) or {}).items():
                    spec=(val or {}).get("version") if isinstance(val,dict) else val
                    if spec: locked.append({"ecosystem":"python","name":name,"version":str(spec).lstrip("="),"source":"Pipfile.lock","scope":scope})
        except Exception as exc: parse_errors.append({"path":"Pipfile.lock","error":str(exc)})
    unique={(_norm_name(x["ecosystem"],x["name"]),x["ecosystem"],x["source"]):x for x in locked}
    return {"locked_dependencies":sorted(unique.values(),key=lambda x:(x["ecosystem"],x["name"],x["source"])),"count":len(unique),"parse_errors":parse_errors}


def world(root: Path) -> dict[str,Any]:
    direct=snapshot(root); locks=lock_snapshot(root)
    by={(x["ecosystem"],_norm_name(x["ecosystem"],x["name"])):x for x in locks["locked_dependencies"]}
    resolved=[]; unlocked=[]
    for dep in direct["direct_dependencies"]:
        item=dict(dep); match=by.get((dep["ecosystem"],_norm_name(dep["ecosystem"],dep["name"])))
        if match:
            item["locked_version"]=match["version"]; item["lock_source"]=match["source"]; item["resolved"]=True; resolved.append(item)
        else:
            item["locked_version"]=None; unlocked.append(item)
    return {"manifests":direct["manifests"],"lockfiles":direct["lockfiles"],"direct_dependencies":direct["direct_dependencies"],
            "locked_dependencies":locks["locked_dependencies"],"resolved_direct":resolved,"unlocked_direct":unlocked,
            "parse_errors":[*direct["parse_errors"],*locks["parse_errors"]],
            "claim_boundary":"Lock-aware direct dependency cognition. It does not compute arbitrary transitive graphs or prove the installed runtime environment matches the lockfile."}

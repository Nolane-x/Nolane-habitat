from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _git(root: Path, args: list[str], timeout: int = 10) -> str:
    proc=subprocess.run(["git","-C",str(root),*args],capture_output=True,text=True,timeout=timeout,shell=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git command failed").strip())
    return proc.stdout


def available(root: Path) -> bool:
    try:
        return _git(root,["rev-parse","--is-inside-work-tree"]).strip()=="true"
    except Exception:
        return False


def status(root: Path) -> dict[str, Any]:
    if not available(root): return {"available":False,"reason":"not-a-git-worktree"}
    branch=_git(root,["rev-parse","--abbrev-ref","HEAD"]).strip()
    head=_git(root,["rev-parse","HEAD"]).strip()
    porcelain=_git(root,["status","--porcelain=v1","-z"])
    entries=[]
    for item in porcelain.split("\0"):
        if not item: continue
        entries.append({"xy":item[:2],"path":item[3:]})
    return {"available":True,"branch":branch,"head":head,"dirty":bool(entries),"changes":entries}


def history(root: Path, path: str | None=None, limit: int=20) -> dict:
    if limit<1 or limit>200: raise ValueError("limit must be in [1,200]")
    if not available(root): return {"available":False,"commits":[]}
    fmt="%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s"
    args=["log",f"-{limit}",f"--format={fmt}"]
    if path: args.extend(["--",path])
    rows=[]
    for line in _git(root,args).splitlines():
        parts=line.split("\x1f")
        if len(parts)>=6:
            rows.append({"commit":parts[0],"parents":[x for x in parts[1].split() if x],"author":parts[2],"author_email":parts[3],"authored_at":parts[4],"subject":parts[5]})
    return {"available":True,"path":path,"count":len(rows),"commits":rows}


def blame(root: Path, path: str, start_line: int=1, end_line: int | None=None) -> dict:
    if start_line<1 or (end_line is not None and end_line<start_line): raise ValueError("invalid line range")
    if not available(root): return {"available":False,"lines":[]}
    spec=f"{start_line},{end_line or start_line}"
    out=_git(root,["blame","--line-porcelain","-L",spec,"--",path])
    lines=[]; cur={}
    for line in out.splitlines():
        if line.startswith("\t"):
            cur["text"]=line[1:]; lines.append(cur); cur={}; continue
        parts=line.split(" ",3)
        if len(parts)>=3 and len(parts[0])>=8 and all(c in "0123456789abcdef" for c in parts[0].lower()):
            cur={"commit":parts[0],"original_line":int(parts[1]),"final_line":int(parts[2])}; continue
        if line.startswith("author "): cur["author"]=line[7:]
        elif line.startswith("author-time "): cur["author_time"]=int(line[12:])
        elif line.startswith("summary "): cur["summary"]=line[8:]
    return {"available":True,"path":path,"start_line":start_line,"end_line":end_line or start_line,"lines":lines}


def explain_line(root: Path, path: str, line: int) -> dict:
    b=blame(root,path,line,line)
    if not b.get("available") or not b.get("lines"): return {**b,"explanation":None}
    item=b["lines"][0]; commit=item["commit"]
    show=_git(root,["show","--no-patch","--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%B",commit])
    parts=show.split("\x1f",5)
    meta={"commit":commit}
    if len(parts)>=6:
        meta.update({"parents":[x for x in parts[1].split() if x],"author":parts[2],"author_email":parts[3],"authored_at":parts[4],"message":parts[5].strip()})
    return {"available":True,"path":path,"line":line,"blame":item,"commit":meta,"claim_boundary":"Git provenance explains historical authorship/change context; it does not prove the current behavioral reason is still valid."}


def diff(root: Path, *, commit: str | None = None, path: str | None = None, context: int = 3, max_bytes: int = 120_000) -> dict:
    if context < 0 or context > 50: raise ValueError("context must be in [0,50]")
    if max_bytes < 1 or max_bytes > 2_000_000: raise ValueError("max_bytes must be in [1,2000000]")
    if not available(root): return {"available":False,"diff":""}
    args=["diff",f"--unified={context}"]
    if commit: args.append(commit)
    if path: args.extend(["--",path])
    out=_git(root,args,timeout=20)
    raw=out.encode("utf-8",errors="replace")
    clipped=raw[:max_bytes].decode("utf-8",errors="replace")
    return {"available":True,"commit":commit,"path":path,"diff":clipped,"truncated":len(raw)>max_bytes,"total_bytes":len(raw)}


def changed_files(root: Path, commit: str = "HEAD", limit: int = 500) -> dict:
    if limit<1 or limit>5000: raise ValueError("limit must be in [1,5000]")
    if not available(root): return {"available":False,"files":[]}
    out=_git(root,["show","--format=","--name-status",commit],timeout=20)
    rows=[]
    for line in out.splitlines():
        if not line.strip(): continue
        parts=line.split("\t")
        status=parts[0]
        if status.startswith(("R","C")) and len(parts)>=3:
            rows.append({"status":status,"from_path":parts[1],"path":parts[2]})
        elif len(parts)>=2:
            rows.append({"status":status,"path":parts[1]})
        if len(rows)>=limit: break
    return {"available":True,"commit":commit,"files":rows,"count":len(rows),"truncated":len(rows)>=limit}


def churn(root: Path, path: str, limit: int = 200) -> dict:
    if limit<1 or limit>2000: raise ValueError("limit must be in [1,2000]")
    if not available(root): return {"available":False}
    fmt="%H%x1f%an%x1f%aI"
    out=_git(root,["log",f"-{limit}",f"--format={fmt}","--numstat","--",path],timeout=25)
    commits=0; authors=set(); additions=deletions=0; last_commit=None; last_at=None
    for line in out.splitlines():
        if "\x1f" in line:
            parts=line.split("\x1f"); commits+=1
            if len(parts)>=3:
                last_commit=last_commit or parts[0]; authors.add(parts[1]); last_at=last_at or parts[2]
            continue
        parts=line.split("\t")
        if len(parts)>=3 and parts[0].isdigit() and parts[1].isdigit():
            additions+=int(parts[0]); deletions+=int(parts[1])
    score=min(1.0, commits/50.0 + (additions+deletions)/5000.0 + max(0,len(authors)-1)/20.0)
    return {"available":True,"path":path,"commits":commits,"authors":sorted(authors),"author_count":len(authors),"additions":additions,"deletions":deletions,
            "last_commit":last_commit,"last_authored_at":last_at,"churn_risk":round(score,4),
            "claim_boundary":"Churn is historical change pressure, not defect probability."}


def explain_symbol(root: Path, path: str, start_line: int, end_line: int) -> dict:
    if start_line<1 or end_line<start_line: raise ValueError("invalid symbol range")
    b=blame(root,path,start_line,end_line)
    commits=[]; seen=set()
    for row in b.get("lines") or []:
        c=row.get("commit")
        if c and c not in seen:
            seen.add(c); commits.append(c)
    history_rows=[]
    for c in commits[:12]:
        try:
            raw=_git(root,["show","--no-patch","--format=%H%x1f%an%x1f%aI%x1f%s",c])
            parts=raw.strip().split("\x1f",3)
            if len(parts)==4: history_rows.append({"commit":parts[0],"author":parts[1],"authored_at":parts[2],"subject":parts[3]})
        except Exception:
            continue
    return {"available":bool(b.get("available")),"path":path,"start_line":start_line,"end_line":end_line,"blame":b.get("lines") or [],"commits":history_rows,
            "churn":churn(root,path),"claim_boundary":"Temporal provenance for the current source region; it does not prove historical intent remains valid."}


def branches(root: Path, limit: int = 200) -> dict[str, Any]:
    if limit < 1 or limit > 2000: raise ValueError("limit must be in [1,2000]")
    if not available(root): return {"available":False,"branches":[]}
    fmt="%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)%09%(committerdate:iso-strict)%09%(subject)"
    out=_git(root,["for-each-ref",f"--count={limit}",f"--format={fmt}","refs/heads"],timeout=20)
    rows=[]
    for line in out.splitlines():
        parts=line.split("\t")
        if len(parts)>=6:
            rows.append({"name":parts[0],"commit":parts[1],"upstream":parts[2] or None,"tracking":parts[3] or None,
                         "committed_at":parts[4],"subject":parts[5]})
    current=_git(root,["branch","--show-current"]).strip() or None
    return {"available":True,"current":current,"count":len(rows),"branches":rows,
            "claim_boundary":"Branch topology and tracking metadata only; remote freshness is not implied without an explicit fetch."}


def worktrees(root: Path) -> dict[str, Any]:
    if not available(root): return {"available":False,"worktrees":[]}
    out=_git(root,["worktree","list","--porcelain"],timeout=20)
    rows=[]; cur={}
    for line in out.splitlines()+[""]:
        if not line:
            if cur: rows.append(cur); cur={}
            continue
        if " " in line:
            key,value=line.split(" ",1)
            if key=="branch" and value.startswith("refs/heads/"): value=value[len("refs/heads/"):]
            cur[key]=value
        else: cur[line]=True
    return {"available":True,"count":len(rows),"worktrees":rows}


def conflicts(root: Path) -> dict[str, Any]:
    if not available(root): return {"available":False,"conflicts":[]}
    out=_git(root,["diff","--name-only","--diff-filter=U"],timeout=20)
    paths=[x.strip() for x in out.splitlines() if x.strip()]
    op=None
    gd=root/".git"
    try:
        gitdir=Path(_git(root,["rev-parse","--git-dir"]).strip())
        if not gitdir.is_absolute(): gitdir=(root/gitdir).resolve()
        if (gitdir/"MERGE_HEAD").exists(): op="merge"
        elif (gitdir/"rebase-merge").exists() or (gitdir/"rebase-apply").exists(): op="rebase"
        elif (gitdir/"CHERRY_PICK_HEAD").exists(): op="cherry-pick"
        elif (gitdir/"REVERT_HEAD").exists(): op="revert"
    except Exception: pass
    return {"available":True,"operation":op,"conflicted":bool(paths),"count":len(paths),"conflicts":paths,
            "claim_boundary":"Reports Git index conflict state; it does not choose or apply a merge resolution."}


def commit_impact(root: Path, commit: str = "HEAD", limit: int = 1000) -> dict[str, Any]:
    if not available(root): return {"available":False,"files":[]}
    files=changed_files(root,commit,limit)
    try:
        raw=_git(root,["show","--stat","--format=%H%x1f%P%x1f%aI%x1f%s",commit],timeout=20)
        first=raw.splitlines()[0] if raw.splitlines() else ""
        parts=first.split("\x1f",3)
        meta={"commit":parts[0] if parts else commit,"parents":parts[1].split() if len(parts)>1 else [],"authored_at":parts[2] if len(parts)>2 else None,"subject":parts[3] if len(parts)>3 else None}
    except Exception: meta={"commit":commit}
    return {"available":True,**meta,"files":files.get("files") or [],"file_count":files.get("count",0),
            "claim_boundary":"Commit-level file impact from Git history; semantic/runtime impact can extend beyond these paths."}

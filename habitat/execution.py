from __future__ import annotations

import importlib.util
import json
import os
import shutil
import signal
import subprocess
import tempfile
import platform
import re
import sys
import time
try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None
from functools import lru_cache
from pathlib import Path

from .model import ExecutionReceipt
from .source_bridge import snapshot_metadata
from .testing.normalize import normalize_test_output
from .util import stable_id

MAX_CAPTURE = 64_000

_SECRET_ENV_RE = re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key|private[_-]?key|credential|aws_|github_|openai_)")

def containment_probe() -> dict:
    unshare=shutil.which("unshare")
    network=False; reason="unshare unavailable"
    if sys.platform.startswith("linux") and unshare:
        try:
            p=subprocess.run([unshare,"-Urn","true"],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=3,shell=False)
            network=(p.returncode==0); reason="user+network namespace available" if network else (p.stderr or "namespace denied").strip()[:300]
        except Exception as exc:
            reason=f"namespace probe failed: {exc}"
    return {
        "network_namespace_available":network,
        "filesystem_confinement_available":False,
        "full_sandbox_available":False,
        "unshare":unshare,
        "reason":reason,
        "claim_boundary":"Network/user namespace availability is partial containment; filesystem isolation is not provided by this provider.",
    }

def _restricted_env() -> dict[str,str]:
    keep={}
    safe_names={"PATH","HOME","USER","LOGNAME","LANG","LC_ALL","LC_CTYPE","TZ","TMPDIR","TEMP","TMP","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT","VIRTUAL_ENV","CONDA_PREFIX","CI"}
    for k,v in os.environ.items():
        if k in safe_names and not _SECRET_ENV_RE.search(k): keep[k]=v
    keep["HABITAT_CONTAINED_EXECUTION"]="1"
    return keep

def _limit_resources():
    # High enough for ordinary tests but finite enough to prevent obvious fork/output/file descriptor bombs.
    if resource is None:
        return
    limits=[
        (resource.RLIMIT_NOFILE,256),
        (resource.RLIMIT_NPROC,256),
        (resource.RLIMIT_FSIZE,512*1024*1024),
        (resource.RLIMIT_CORE,0),
    ]
    for which,value in limits:
        try: resource.setrlimit(which,(value,value))
        except Exception: pass

_SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(authorization\s*:\s*bearer)\s+[^\s]+"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)\b(\s*[:=]\s*)[^\s,;]+"), r"\1\2[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
]

def _redact_output(text: str) -> tuple[str, int]:
    count=0
    for regex,repl in _SECRET_PATTERNS:
        text,n=regex.subn(repl,text); count+=n
    return text,count


def _project_python(root: Path) -> str:
    candidates = [
        root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
    ]
    for p in candidates:
        if p.is_file() and (os.name == "nt" or os.access(p, os.X_OK)):
            return str(p)
    return sys.executable

def _python_has_module(exe: str, module: str) -> bool:
    try:
        proc=subprocess.run([exe,"-c",f"import {module}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5,shell=False)
        return proc.returncode == 0
    except Exception:
        return False



@lru_cache(maxsize=32)
def _tool_version(exe: str) -> str | None:
    try:
        p = subprocess.run([exe, "--version"], text=True, capture_output=True, timeout=3, shell=False)
        value = (p.stdout or p.stderr or "").strip().splitlines()
        return value[0][:200] if value else None
    except Exception:
        return None


def _cap(id_: str, kind: str, argv: list[str], confidence: str, available: bool, reason: str) -> dict:
    exe = argv[0] if argv else ""
    return {
        "id": id_, "kind": kind, "argv": argv, "confidence": confidence,
        "available": available, "availability_reason": reason,
        "toolchain": {"executable": exe, "version": _tool_version(exe) if available and exe else None},
    }


def discover_capabilities(root: Path) -> list[dict]:
    caps: list[dict] = []
    tests_dir = root / "tests"
    if tests_dir.exists():
        project_python = _project_python(root)
        python_origin = "project-environment" if Path(project_python).resolve() != Path(sys.executable).resolve() else "host-interpreter-fallback"
        caps.append(_cap(
            "python.unittest", "test", [project_python, "-m", "unittest", "discover", "-s", "tests", "-v"],
            python_origin, True, f"Python unittest via {python_origin}",
        ))
        pytest_present = _python_has_module(project_python,"pytest")
        caps.append(_cap(
            "python.pytest", "test", [project_python, "-m", "pytest", "-q"],
            python_origin, pytest_present,
            f"pytest importable in {python_origin}" if pytest_present else f"pytest not importable in {python_origin}",
        ))
    pkg = root / "package.json"
    if pkg.exists():
        npm = shutil.which("npm")
        try:
            value = json.loads(pkg.read_text(encoding="utf-8"))
            for name in value.get("scripts", {}):
                lname = name.lower()
                kind = "test" if any(x in lname for x in ("test", "spec")) else "build" if any(x in lname for x in ("build", "compile", "bundle")) else "service" if any(x in lname for x in ("dev", "serve", "start")) else "script"
                caps.append(_cap(
                    f"npm.{name}", kind, [npm or "npm", "run", name], "exact-manifest",
                    npm is not None, "npm executable found" if npm else "npm executable not found",
                ))
        except Exception:
            pass
    if (root / "pom.xml").exists():
        mvn = shutil.which("mvn")
        for id_, goal, kind in [("maven.test", "test", "test"), ("maven.package", "package", "build")]:
            caps.append(_cap(id_, kind, [mvn or "mvn", goal], "exact-manifest", mvn is not None,
                             "mvn executable found" if mvn else "mvn executable not found"))
    if (root / "gradlew").exists() or (root / "gradlew.bat").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        if os.name == "nt" and (root / "gradlew.bat").exists():
            exe = str(root / "gradlew.bat"); available = True; reason = "project Gradle wrapper found"
        elif (root / "gradlew").exists():
            exe = str(root / "gradlew"); available = os.access(root / "gradlew", os.X_OK); reason = "project Gradle wrapper found" if available else "gradlew is not executable"
        else:
            gradle = shutil.which("gradle"); exe = gradle or "gradle"; available = gradle is not None; reason = "gradle executable found" if gradle else "no Gradle wrapper/executable found"
        for id_, goal, kind in [("gradle.test", "test", "test"), ("gradle.build", "build", "build")]:
            caps.append(_cap(id_, kind, [exe, goal], "exact-manifest", available, reason))
    return caps


def run_action(root: Path, capability: str, argv: list[str], timeout_s: int = 60, capability_kind: str | None = None, containment_profile: str = "trusted-local") -> ExecutionReceipt:
    before = snapshot_metadata(root)
    started = time.monotonic(); timed_out=False; exit_code=None
    if containment_profile not in {"trusted-local","network-contained"}:
        raise ValueError("containment_profile must be trusted-local or network-contained")
    probe=containment_probe() if containment_profile=="network-contained" else None
    effective_argv=list(argv)
    network_restricted=False
    if containment_profile=="network-contained":
        if not probe or not probe.get("network_namespace_available"):
            raise RuntimeError("network-contained execution unavailable: "+str((probe or {}).get("reason")))
        effective_argv=[str(probe["unshare"]),"-Urn","--fork","--",*argv]
        network_restricted=True
    environment_fingerprint={
        "os":platform.system(),"os_release":platform.release(),"architecture":platform.machine(),
        "python_version":platform.python_version(),"python_executable":sys.executable,
        "argv0":argv[0] if argv else None,"cwd":str(root),
        "environment_keys":sorted(k for k in os.environ if k in {"CI","LANG","LC_ALL","TZ","VIRTUAL_ENV","CONDA_PREFIX"}),
        "security_profile":containment_profile,
        "sandboxed":False,"network_restricted":network_restricted,"filesystem_restricted":False,
        "resource_limited":containment_profile=="network-contained",
        "secret_environment_scrubbed":containment_profile=="network-contained",
        "claim_boundary":"network-contained isolates network/user namespace and applies process limits; it does not confine filesystem reads/writes",
    }
    popen_kwargs=dict(cwd=root,stdout=None,stderr=None,shell=False)
    if containment_profile=="network-contained":
        popen_kwargs["env"]=_restricted_env()
        if os.name!="nt": popen_kwargs["preexec_fn"]=_limit_resources
    if os.name!="nt": popen_kwargs["start_new_session"]=True
    else: popen_kwargs["creationflags"]=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
    with tempfile.TemporaryDirectory(prefix="habitat-run-") as td:
        outp=Path(td)/"stdout.bin"; errp=Path(td)/"stderr.bin"
        with outp.open("wb") as out_f, errp.open("wb") as err_f:
            popen_kwargs["stdout"]=out_f; popen_kwargs["stderr"]=err_f
            proc=subprocess.Popen(effective_argv,**popen_kwargs)
            try:
                proc.wait(timeout=timeout_s); exit_code=proc.returncode
            except subprocess.TimeoutExpired:
                timed_out=True
                if os.name!="nt":
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                else: proc.kill()
                proc.wait(); exit_code=proc.returncode
        stdout_total=outp.stat().st_size if outp.exists() else 0; stderr_total=errp.stat().st_size if errp.exists() else 0
        stdout=(outp.read_bytes()[:MAX_CAPTURE] if outp.exists() else b"").decode("utf-8",errors="replace")
        stderr=(errp.read_bytes()[:MAX_CAPTURE] if errp.exists() else b"").decode("utf-8",errors="replace")
        stdout, stdout_redactions = _redact_output(stdout)
        stderr, stderr_redactions = _redact_output(stderr)
    duration=int((time.monotonic()-started)*1000)
    after=snapshot_metadata(root); changed=sorted(set(before)|set(after),key=str); changed=[p for p in changed if before.get(p)!=after.get(p)]
    structured=normalize_test_output(capability,stdout,stderr,exit_code,timed_out) if capability_kind=="test" else None
    if structured is not None:
        structured["environment_fingerprint"]=environment_fingerprint
    return ExecutionReceipt(
        id=stable_id("run",capability,str(time.time_ns())),capability=capability,argv=argv,cwd=str(root),
        exit_code=exit_code,timed_out=timed_out,duration_ms=duration,stdout=stdout,stderr=stderr,
        stdout_truncated=stdout_total>MAX_CAPTURE,stderr_truncated=stderr_total>MAX_CAPTURE,changed_paths=changed,structured=structured,
        stdout_total_bytes=int(stdout_total),stderr_total_bytes=int(stderr_total),environment_fingerprint=environment_fingerprint,
        redaction={"stdout_matches":int(stdout_redactions),"stderr_matches":int(stderr_redactions),
                   "policy":"conservative common-secret patterns; not a complete DLP system"},
    )


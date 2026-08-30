from __future__ import annotations

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
from typing import Mapping

from .model import ExecutionReceipt
from .security.containment import ContainmentAttestation, ProbeReceipt, unverified_attestation
from .source_bridge import snapshot_metadata
from .testing.normalize import normalize_test_output
from .util import HARD_IGNORE_DIRS, stable_id

MAX_CAPTURE = 64_000
_SECRET_ENV_RE = re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key|private[_-]?key|credential|aws_|github_|openai_)")


def containment_probe() -> dict:
    unshare = shutil.which("unshare")
    network = False
    reason = "unshare unavailable"
    if sys.platform.startswith("linux") and unshare:
        try:
            p = subprocess.run(
                [unshare, "-Urn", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
                shell=False,
            )
            network = p.returncode == 0
            reason = "user+network namespace available" if network else (p.stderr or "namespace denied").strip()[:300]
        except Exception as exc:
            reason = f"namespace probe failed: {exc}"
    return {
        "network_namespace_available": network,
        "user_namespace_available": network,
        "filesystem_confinement_available": False,
        "full_sandbox_available": False,
        "unshare": unshare,
        "reason": reason,
        "claim_boundary": "Network/user namespace availability is partial containment; filesystem isolation is not provided by this provider.",
    }


def _restricted_env(source_env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if source_env is None else source_env
    keep: dict[str, str] = {}
    safe_names = {
        "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
        "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
        "VIRTUAL_ENV", "CONDA_PREFIX", "CI",
    }
    for key, value in source.items():
        if key in safe_names and not _SECRET_ENV_RE.search(key):
            keep[key] = value
    keep["HABITAT_CONTAINED_EXECUTION"] = "1"
    return keep


def secret_boundary_probe() -> dict:
    synthetic = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "C"),
        "HABITAT_API_KEY": "wave6-probe-secret",
        "GITHUB_TOKEN": "wave6-probe-token",
    }
    restricted = _restricted_env(synthetic)
    success = (
        "HABITAT_API_KEY" not in restricted
        and "GITHUB_TOKEN" not in restricted
        and restricted.get("HABITAT_CONTAINED_EXECUTION") == "1"
    )
    return {
        "available": success,
        "mechanism": "restricted-environment-allowlist",
        "reason": "synthetic secret keys removed by restricted environment policy" if success else "restricted environment policy failed synthetic secret probe",
    }


def _resource_limit_specs() -> list[tuple[str, int, int]]:
    if resource is None:
        return []
    specs: list[tuple[str, int, int]] = []
    for name, attr, requested in (
        ("nofile", "RLIMIT_NOFILE", 256),
        ("nproc", "RLIMIT_NPROC", 256),
        ("fsize", "RLIMIT_FSIZE", 512 * 1024 * 1024),
        ("core", "RLIMIT_CORE", 0),
    ):
        if hasattr(resource, attr):
            specs.append((name, int(getattr(resource, attr)), requested))
    return specs


def _strict_resource_limit_preexec() -> None:
    """Install finite resource limits in the child process or fail closed."""
    if resource is None:
        raise RuntimeError("POSIX resource module unavailable")
    specs = _resource_limit_specs()
    names = {name for name, _, _ in specs}
    required = {"nofile", "fsize", "core"}
    if not required.issubset(names):
        raise RuntimeError("required POSIX resource limits unavailable")

    for name, which, requested in specs:
        _soft, hard = resource.getrlimit(which)
        if hard == resource.RLIM_INFINITY:
            target = requested
        else:
            target = min(requested, int(hard))
        if target < 0:
            raise RuntimeError(f"invalid hard limit for {name}")
        resource.setrlimit(which, (target, target))
        observed_soft, observed_hard = resource.getrlimit(which)
        if int(observed_soft) != int(target) or int(observed_hard) != int(target):
            raise RuntimeError(f"failed to enforce resource limit: {name}")


def _limit_resources() -> None:
    """Compatibility alias for the strict child-only limiter."""
    _strict_resource_limit_preexec()


def resource_limit_probe() -> dict:
    if os.name == "nt" or resource is None:
        return {
            "available": False,
            "attempted": False,
            "mechanism": "posix-rlimit",
            "verified_limits": [],
            "observed": {},
            "reason": "POSIX resource limits unavailable on this host",
        }

    specs = _resource_limit_specs()
    names = [name for name, _, _ in specs]
    required = {"nofile", "fsize", "core"}
    if not required.issubset(names):
        return {
            "available": False,
            "attempted": False,
            "mechanism": "posix-rlimit",
            "verified_limits": [],
            "observed": {},
            "reason": "required POSIX resource limit constants unavailable",
        }

    script = r'''
import json, resource
items = [
    ("nofile", "RLIMIT_NOFILE"),
    ("nproc", "RLIMIT_NPROC"),
    ("fsize", "RLIMIT_FSIZE"),
    ("core", "RLIMIT_CORE"),
]
out = {}
for name, attr in items:
    if hasattr(resource, attr):
        soft, hard = resource.getrlimit(getattr(resource, attr))
        out[name] = {"soft": int(soft), "hard": int(hard)}
print(json.dumps(out, sort_keys=True))
'''
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
            preexec_fn=_strict_resource_limit_preexec,
        )
    except Exception as exc:
        return {
            "available": False,
            "attempted": True,
            "mechanism": "posix-rlimit",
            "verified_limits": [],
            "observed": {},
            "reason": f"strict resource-limit child probe failed: {type(exc).__name__}: {exc}",
        }
    if proc.returncode != 0:
        return {
            "available": False,
            "attempted": True,
            "mechanism": "posix-rlimit",
            "verified_limits": [],
            "observed": {},
            "reason": (proc.stderr or proc.stdout or "resource-limit child returned non-zero").strip()[:500],
        }
    try:
        observed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "available": False,
            "attempted": True,
            "mechanism": "posix-rlimit",
            "verified_limits": [],
            "observed": {},
            "reason": f"resource-limit child emitted invalid JSON: {exc}",
        }

    verified: list[str] = []
    for name in names:
        item = observed.get(name)
        if not isinstance(item, dict):
            continue
        soft = item.get("soft")
        hard = item.get("hard")
        if isinstance(soft, int) and isinstance(hard, int) and soft >= 0 and hard >= 0:
            verified.append(name)
    success = required.issubset(verified) and ("nproc" not in names or "nproc" in verified)
    return {
        "available": bool(success),
        "attempted": True,
        "mechanism": "posix-rlimit",
        "verified_limits": verified,
        "observed": observed,
        "reason": "strict child resource limits observed" if success else "one or more strict child resource limits were not observed",
    }


def _direct_network_attestation(namespace_probe: dict) -> ContainmentAttestation:
    provider_id = "execution:direct"
    provider_version = "run-action-network-contained-v1"
    limits = resource_limit_probe()
    secrets = secret_boundary_probe()
    network_ok = bool(namespace_probe.get("network_namespace_available"))
    user_ok = bool(namespace_probe.get("user_namespace_available", network_ok))
    namespace_attempted = bool(namespace_probe.get("unshare")) or network_ok or user_ok
    limit_ok = bool(limits.get("available"))
    limit_attempted = bool(limits.get("attempted", bool(limits.get("mechanism")))) or limit_ok
    secret_ok = bool(secrets.get("available"))
    namespace_reason = str(namespace_probe.get("reason") or "network/user namespace probe unavailable")
    limit_reason = str(limits.get("reason") or "resource-limit probe unavailable")
    secret_reason = str(secrets.get("reason") or "secret-boundary probe unavailable")
    receipts = (
        ProbeReceipt(f"{provider_id}:probe:network", provider_id, "network_isolation", "linux-unshare-user-network", namespace_attempted, network_ok, namespace_reason),
        ProbeReceipt(f"{provider_id}:probe:user", provider_id, "user_isolation", "linux-unshare-user-network", namespace_attempted, user_ok, namespace_reason),
        ProbeReceipt(f"{provider_id}:probe:resource", provider_id, "resource_limits", str(limits.get("mechanism") or "posix-rlimit"), limit_attempted, limit_ok, limit_reason),
        ProbeReceipt(f"{provider_id}:probe:secret", provider_id, "secret_boundary", str(secrets.get("mechanism") or "restricted-environment-allowlist"), True, secret_ok, secret_reason),
    )
    return ContainmentAttestation(
        provider_id=provider_id,
        provider_version=provider_version,
        process_isolation=False,
        filesystem_isolation=False,
        network_isolation=network_ok,
        user_isolation=user_ok,
        capability_drop=False,
        resource_limits=limit_ok,
        secret_boundary=secret_ok,
        probe_receipts=receipts,
        claim_boundary="direct network-contained execution proves only successful user/network namespace, strict POSIX resource-limit, and restricted-environment controls; filesystem and process isolation are not provided",
    )


def bind_containment_attestation(
    receipt: ExecutionReceipt,
    attestation: ContainmentAttestation,
    *,
    security_profile: str | None = None,
) -> ExecutionReceipt:
    """Bind one typed containment authority to an execution receipt and its legacy projection."""
    fp = dict(receipt.environment_fingerprint or {})
    full_sandbox = all((
        attestation.process_isolation,
        attestation.filesystem_isolation,
        attestation.network_isolation,
        attestation.user_isolation,
        attestation.capability_drop,
    ))
    fp.update({
        "containment_attestation": attestation.as_dict(),
        "containment_attestation_fingerprint": attestation.fingerprint,
        "sandboxed": bool(full_sandbox),
        "network_restricted": attestation.network_isolation,
        "filesystem_restricted": attestation.filesystem_isolation,
        "process_isolated": attestation.process_isolation,
        "user_isolated": attestation.user_isolation,
        "capabilities_dropped": attestation.capability_drop,
        "resource_limited": attestation.resource_limits,
        "secret_environment_scrubbed": attestation.secret_boundary,
        "claim_boundary": attestation.claim_boundary,
    })
    if security_profile is not None:
        fp["security_profile"] = security_profile
    receipt.environment_fingerprint = fp
    if receipt.structured is not None:
        receipt.structured["environment_fingerprint"] = dict(fp)
    return receipt


_SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(authorization\s*:\s*bearer)\s+[^\s]+"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)\b(\s*[:=]\s*)[^\s,;]+"), r"\1\2[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
]


def _redact_output(text: str) -> tuple[str, int]:
    count = 0
    for regex, repl in _SECRET_PATTERNS:
        text, n = regex.subn(repl, text)
        count += n
    return text, count


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
        probe = "import importlib.util,sys; raise SystemExit(0 if importlib.util.find_spec(sys.argv[1]) else 1)"
        proc = subprocess.run([exe, "-c", probe, module], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, shell=False)
        return proc.returncode == 0
    except Exception:
        return False


def _prepare_python_bytecode_cache(root: Path) -> None:
    """Remove project bytecode without touching virtual environments or dependencies."""
    for directory, dirnames, _ in os.walk(root):
        if "__pycache__" in dirnames:
            cache_dir = Path(directory) / "__pycache__"
            try:
                if not cache_dir.is_symlink():
                    shutil.rmtree(cache_dir)
            except OSError:
                pass
            dirnames.remove("__pycache__")
        dirnames[:] = [name for name in dirnames if name not in HARD_IGNORE_DIRS]


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
        pytest_present = _python_has_module(project_python, "pytest")
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
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            caps.append(_cap(
                "npm.manifest",
                "metadata",
                [],
                "exact-manifest",
                False,
                f"package.json is invalid or unreadable: {type(exc).__name__}",
            ))
    if (root / "pom.xml").exists():
        mvn = shutil.which("mvn")
        for id_, goal, kind in [("maven.test", "test", "test"), ("maven.package", "package", "build")]:
            caps.append(_cap(id_, kind, [mvn or "mvn", goal], "exact-manifest", mvn is not None,
                             "mvn executable found" if mvn else "mvn executable not found"))
    if (root / "gradlew").exists() or (root / "gradlew.bat").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        if os.name == "nt" and (root / "gradlew.bat").exists():
            exe = str(root / "gradlew.bat")
            available = True
            reason = "project Gradle wrapper found"
        elif (root / "gradlew").exists():
            exe = str(root / "gradlew")
            available = os.access(root / "gradlew", os.X_OK)
            reason = "project Gradle wrapper found" if available else "gradlew is not executable"
        else:
            gradle = shutil.which("gradle")
            exe = gradle or "gradle"
            available = gradle is not None
            reason = "gradle executable found" if gradle else "no Gradle wrapper/executable found"
        for id_, goal, kind in [("gradle.test", "test", "test"), ("gradle.build", "build", "build")]:
            caps.append(_cap(id_, kind, [exe, goal], "exact-manifest", available, reason))
    return caps


def run_action(
    root: Path,
    capability: str,
    argv: list[str],
    timeout_s: int = 60,
    capability_kind: str | None = None,
    containment_profile: str = "trusted-local",
    *,
    apply_resource_limits: bool = False,
    containment_attestation: ContainmentAttestation | None = None,
) -> ExecutionReceipt:
    before = snapshot_metadata(root)
    started = time.monotonic()
    timed_out = False
    exit_code = None
    if containment_profile not in {"trusted-local", "network-contained"}:
        raise ValueError("containment_profile must be trusted-local or network-contained")
    probe = containment_probe() if containment_profile == "network-contained" else None
    effective_argv = list(argv)
    if containment_profile == "network-contained":
        if not probe or not probe.get("network_namespace_available"):
            raise RuntimeError("network-contained execution unavailable: " + str((probe or {}).get("reason")))
        effective_argv = [str(probe["unshare"]), "-Urn", "--fork", "--", *argv]

    attestation = containment_attestation
    if attestation is None:
        if containment_profile == "network-contained":
            attestation = _direct_network_attestation(probe or {})
        else:
            attestation = unverified_attestation(
                "execution:direct",
                "run-action-v1",
                "direct trusted-local run_action call has no provider-bound containment evidence",
            )

    limits_requested = containment_profile == "network-contained" or bool(apply_resource_limits)
    if attestation.resource_limits and not limits_requested:
        raise RuntimeError("resource-limit attestation is true but this execution did not request strict resource limits")
    if limits_requested and (os.name == "nt" or resource is None):
        raise RuntimeError("strict resource-limited execution is unavailable on this host")

    environment_fingerprint = {
        "os": platform.system(), "os_release": platform.release(), "architecture": platform.machine(),
        "python_version": platform.python_version(), "python_executable": sys.executable,
        "argv0": argv[0] if argv else None, "cwd": str(root),
        "environment_keys": sorted(k for k in os.environ if k in {"CI", "LANG", "LC_ALL", "TZ", "VIRTUAL_ENV", "CONDA_PREFIX"}),
        "security_profile": containment_profile,
    }
    popen_kwargs = dict(cwd=root, stdout=None, stderr=None, shell=False)
    if containment_profile == "network-contained":
        popen_kwargs["env"] = _restricted_env()
    if limits_requested:
        popen_kwargs["preexec_fn"] = _strict_resource_limit_preexec
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with tempfile.TemporaryDirectory(prefix="habitat-run-") as td:
        outp = Path(td) / "stdout.bin"
        errp = Path(td) / "stderr.bin"
        if capability.startswith("python."):
            _prepare_python_bytecode_cache(root)
            execution_env = dict(popen_kwargs.get("env") or os.environ)
            execution_env.pop("PYTHONPYCACHEPREFIX", None)
            execution_env["PYTHONDONTWRITEBYTECODE"] = "1"
            popen_kwargs["env"] = execution_env
        with outp.open("wb") as out_f, errp.open("wb") as err_f:
            popen_kwargs["stdout"] = out_f
            popen_kwargs["stderr"] = err_f
            proc = subprocess.Popen(effective_argv, **popen_kwargs)
            try:
                proc.wait(timeout=timeout_s)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name != "nt":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.wait()
                exit_code = proc.returncode
        stdout_total = outp.stat().st_size if outp.exists() else 0
        stderr_total = errp.stat().st_size if errp.exists() else 0
        stdout = (outp.read_bytes()[:MAX_CAPTURE] if outp.exists() else b"").decode("utf-8", errors="replace")
        stderr = (errp.read_bytes()[:MAX_CAPTURE] if errp.exists() else b"").decode("utf-8", errors="replace")
        stdout, stdout_redactions = _redact_output(stdout)
        stderr, stderr_redactions = _redact_output(stderr)
    duration = int((time.monotonic() - started) * 1000)
    after = snapshot_metadata(root)
    changed = sorted(set(before) | set(after), key=str)
    changed = [p for p in changed if before.get(p) != after.get(p)]
    structured = normalize_test_output(capability, stdout, stderr, exit_code, timed_out) if capability_kind == "test" else None
    receipt = ExecutionReceipt(
        id=stable_id("run", capability, str(time.time_ns())), capability=capability, argv=argv, cwd=str(root),
        exit_code=exit_code, timed_out=timed_out, duration_ms=duration, stdout=stdout, stderr=stderr,
        stdout_truncated=stdout_total > MAX_CAPTURE, stderr_truncated=stderr_total > MAX_CAPTURE, changed_paths=changed, structured=structured,
        stdout_total_bytes=int(stdout_total), stderr_total_bytes=int(stderr_total), environment_fingerprint=environment_fingerprint,
        redaction={"stdout_matches": int(stdout_redactions), "stderr_matches": int(stderr_redactions),
                   "policy": "conservative common-secret patterns; not a complete DLP system"},
    )
    return bind_containment_attestation(receipt, attestation, security_profile=containment_profile)


def validate_containment_binding(
    receipt: ExecutionReceipt,
    *,
    expected_provider_id: str | None = None,
) -> ContainmentAttestation:
    """Validate typed containment evidence serialized into an execution receipt.

    This is a consistency/integrity check over Habitat-authored evidence, not a signature or MAC.
    """
    fingerprint = receipt.environment_fingerprint
    if not isinstance(fingerprint, dict):
        raise RuntimeError("containment receipt has no environment fingerprint")
    raw = fingerprint.get("containment_attestation")
    stored_fingerprint = fingerprint.get("containment_attestation_fingerprint")
    if not isinstance(raw, dict) or not isinstance(stored_fingerprint, str):
        raise RuntimeError("containment receipt is missing typed attestation binding")

    try:
        raw_receipts = raw["probe_receipts"]
        if not isinstance(raw_receipts, list):
            raise TypeError("probe_receipts must be list")
        receipts = tuple(
            ProbeReceipt(
                receipt_id=item["receipt_id"],
                provider_id=item["provider_id"],
                control=item["control"],
                mechanism=item["mechanism"],
                attempted=item["attempted"],
                success=item["success"],
                detail=item["detail"],
            )
            for item in raw_receipts
        )
        attestation = ContainmentAttestation(
            provider_id=raw["provider_id"],
            provider_version=raw["provider_version"],
            process_isolation=raw["process_isolation"],
            filesystem_isolation=raw["filesystem_isolation"],
            network_isolation=raw["network_isolation"],
            user_isolation=raw["user_isolation"],
            capability_drop=raw["capability_drop"],
            resource_limits=raw["resource_limits"],
            secret_boundary=raw["secret_boundary"],
            probe_receipts=receipts,
            claim_boundary=raw["claim_boundary"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid containment attestation in receipt: {exc}") from exc

    if attestation.as_dict() != raw:
        raise RuntimeError("containment attestation serialization is non-canonical")
    if attestation.fingerprint != stored_fingerprint:
        raise RuntimeError("containment attestation fingerprint mismatch")
    if expected_provider_id is not None and attestation.provider_id != expected_provider_id:
        raise RuntimeError("containment attestation provider mismatch")

    full_sandbox = all((
        attestation.process_isolation,
        attestation.filesystem_isolation,
        attestation.network_isolation,
        attestation.user_isolation,
        attestation.capability_drop,
    ))
    expected_projection = {
        "sandboxed": bool(full_sandbox),
        "network_restricted": attestation.network_isolation,
        "filesystem_restricted": attestation.filesystem_isolation,
        "process_isolated": attestation.process_isolation,
        "user_isolated": attestation.user_isolation,
        "capabilities_dropped": attestation.capability_drop,
        "resource_limited": attestation.resource_limits,
        "secret_environment_scrubbed": attestation.secret_boundary,
        "claim_boundary": attestation.claim_boundary,
    }
    for key, expected in expected_projection.items():
        if fingerprint.get(key) != expected:
            raise RuntimeError(f"containment legacy projection mismatch: {key}")
    return attestation

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .execution import discover_capabilities, run_action


def bubblewrap_probe() -> dict[str, Any]:
    exe = shutil.which("bwrap")
    if not exe:
        return {
            "available": False,
            "executable": None,
            "filesystem_confinement": False,
            "network_confinement": False,
            "reason": "bubblewrap executable not found",
        }
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=3, shell=False)
        version = (ver.stdout or ver.stderr or "").strip()[:200]
    except Exception as exc:
        version = None
        return {"available": False, "executable": exe, "filesystem_confinement": False, "network_confinement": False, "reason": f"bubblewrap probe failed: {exc}"}
    # Capability probe must not claim a security boundary unless a minimal namespace launch succeeds.
    try:
        proc = subprocess.run(
            [exe, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net", "--cap-drop", "ALL",
             "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--", "/usr/bin/true"],
            capture_output=True, text=True, timeout=5, shell=False,
        )
        ok = proc.returncode == 0
        reason = "minimal namespace/mount probe passed" if ok else (proc.stderr or proc.stdout or "bubblewrap probe returned non-zero").strip()[:500]
    except Exception as exc:
        ok = False; reason = str(exc)
    return {
        "available": bool(ok), "executable": exe, "version": version,
        "filesystem_confinement": bool(ok), "network_confinement": bool(ok),
        "pid_namespace": bool(ok), "user_namespace": bool(ok),
        "reason": reason,
        "claim_boundary": "Probe proves this host can launch Habitat's minimal bwrap profile; it is not a proof against kernel/runtime vulnerabilities.",
    }


def _visible_host_paths() -> list[str]:
    # Read-only runtime dependencies. Avoid exposing /home, /root, /mnt, /media, /run/user.
    paths = []
    for p in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/alternatives"):
        if Path(p).exists():
            paths.append(p)
    return paths


def build_bwrap_command(root: Path, argv: list[str], *, network: bool = False) -> list[str]:
    probe = bubblewrap_probe()
    if not probe.get("available"):
        raise RuntimeError("filesystem-contained execution unavailable: " + str(probe.get("reason")))
    exe = str(probe["executable"])
    root = root.resolve()
    cmd = [exe, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--cap-drop", "ALL"]
    if not network:
        cmd += ["--unshare-net"]
    for p in _visible_host_paths():
        cmd += ["--ro-bind", p, p]
    cmd += [
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/tmp/habitat-home",
        "--dir", "/workspace", "--bind", str(root), "/workspace", "--chdir", "/workspace",
        "--clearenv", "--setenv", "HOME", "/tmp/habitat-home", "--setenv", "TMPDIR", "/tmp",
        "--setenv", "PATH", os.environ.get("PATH", "/usr/bin:/bin"), "--setenv", "HABITAT_FULL_SANDBOX", "1",
    ]
    rewritten = []
    for arg in argv:
        try:
            ap = Path(arg)
            if ap.is_absolute() and (ap == root or root in ap.parents):
                rewritten.append("/workspace/" + ap.relative_to(root).as_posix())
            else:
                rewritten.append(arg)
        except Exception:
            rewritten.append(arg)
    return [*cmd, "--", *rewritten]


def run_bwrap_action(root: Path, capability: dict, timeout_s: int = 60, argv_override: list[str] | None = None):
    argv = list(argv_override or capability["argv"])
    wrapped = build_bwrap_command(root, argv, network=False)
    receipt = run_action(root, capability["id"], wrapped, timeout_s, capability.get("kind"), "trusted-local")
    # Keep logical argv separate from transport wrapper and explicitly bind the observed security posture.
    receipt.argv = argv
    fp = dict(receipt.environment_fingerprint or {})
    fp.update({
        "security_profile": "filesystem-contained",
        "sandboxed": True,
        "network_restricted": True,
        "filesystem_restricted": True,
        "resource_limited": True,
        "secret_environment_scrubbed": True,
        "sandbox_primitive": "bubblewrap",
        "capabilities_dropped": True,
        "custom_seccomp_filter": False,
        "claim_boundary": "bubblewrap mount/user/pid/ipc/uts/network namespaces, dropped capabilities, a minimal read-only host view and writable project root; no Habitat custom seccomp filter is installed and kernel/bubblewrap vulnerabilities remain outside the proof boundary",
    })
    receipt.environment_fingerprint = fp
    return receipt


def sandbox_capability_summary(root: Path) -> dict[str, Any]:
    b = bubblewrap_probe()
    return {
        "bubblewrap": b,
        "full_sandbox_available": bool(b.get("available")),
        "recommended_untrusted_profile": "filesystem-contained" if b.get("available") else None,
        "capabilities": discover_capabilities(root),
    }

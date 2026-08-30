from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .execution import bind_containment_attestation, discover_capabilities, run_action
from .security.containment import ContainmentAttestation, unverified_attestation


def bubblewrap_probe() -> dict[str, Any]:
    exe = shutil.which("bwrap")
    if not exe:
        return {
            "available": False,
            "executable": None,
            "filesystem_confinement": False,
            "network_confinement": False,
            "pid_namespace": False,
            "user_namespace": False,
            "capabilities_dropped": False,
            "secret_environment_scrubbed": False,
            "reason": "bubblewrap executable not found",
        }
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=3, shell=False)
        version = (ver.stdout or ver.stderr or "").strip()[:200]
    except Exception as exc:
        return {
            "available": False,
            "executable": exe,
            "version": None,
            "filesystem_confinement": False,
            "network_confinement": False,
            "pid_namespace": False,
            "user_namespace": False,
            "capabilities_dropped": False,
            "secret_environment_scrubbed": False,
            "reason": f"bubblewrap probe failed: {exc}",
        }

    # Mechanically exercise the same namespace/mount/cap-drop/clear-env primitives used by Habitat.
    probe_env = dict(os.environ)
    probe_env["HABITAT_BWRAP_PROBE_SECRET"] = "wave6-probe-secret"
    try:
        proc = subprocess.run(
            [
                exe,
                "--die-with-parent", "--new-session",
                "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
                "--cap-drop", "ALL",
                "--ro-bind", "/usr", "/usr",
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                "--clearenv", "--setenv", "HABITAT_BWRAP_PROBE_MARKER", "1",
                "--", "/usr/bin/env",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
            env=probe_env,
        )
        launch_ok = proc.returncode == 0
        env_lines = set((proc.stdout or "").splitlines())
        secret_scrubbed = (
            launch_ok
            and "HABITAT_BWRAP_PROBE_MARKER=1" in env_lines
            and not any(line.startswith("HABITAT_BWRAP_PROBE_SECRET=") for line in env_lines)
        )
        ok = launch_ok and secret_scrubbed
        if ok:
            reason = "namespace/mount/cap-drop/clear-env probe passed"
        elif launch_ok:
            reason = "bubblewrap clear-env probe did not preserve the expected boundary"
        else:
            reason = (proc.stderr or proc.stdout or "bubblewrap probe returned non-zero").strip()[:500]
    except Exception as exc:
        ok = False
        secret_scrubbed = False
        reason = str(exc)
    return {
        "available": bool(ok),
        "executable": exe,
        "version": version,
        "filesystem_confinement": bool(ok),
        "network_confinement": bool(ok),
        "pid_namespace": bool(ok),
        "user_namespace": bool(ok),
        "capabilities_dropped": bool(ok),
        "secret_environment_scrubbed": bool(secret_scrubbed),
        "reason": reason,
        "claim_boundary": "Probe proves this host can launch Habitat's namespace/mount/cap-drop/clear-env bwrap profile; it is not a proof against kernel/runtime or Bubblewrap vulnerabilities and no Habitat custom seccomp filter is installed.",
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


def run_bwrap_action(
    root: Path,
    capability: dict,
    timeout_s: int = 60,
    argv_override: list[str] | None = None,
    *,
    containment_attestation: ContainmentAttestation | None = None,
):
    argv = list(argv_override or capability["argv"])
    wrapped = build_bwrap_command(root, argv, network=False)
    attestation = containment_attestation or unverified_attestation(
        "execution:bubblewrap-direct",
        "bubblewrap-direct-v1",
        "direct Bubblewrap execution has no provider-bound containment evidence; provider attestation is required for verified claims",
    )
    receipt = run_action(
        root,
        capability["id"],
        wrapped,
        timeout_s,
        capability.get("kind"),
        "trusted-local",
        apply_resource_limits=attestation.resource_limits,
        containment_attestation=attestation,
    )
    # Keep logical argv separate from the transport wrapper. All legacy security booleans are
    # projected by the typed attestation; this layer only adds Bubblewrap transport metadata.
    receipt.argv = argv
    bind_containment_attestation(receipt, attestation, security_profile="filesystem-contained")
    fp = dict(receipt.environment_fingerprint or {})
    fp.update({
        "sandbox_primitive": "bubblewrap",
        "custom_seccomp_filter": False,
    })
    receipt.environment_fingerprint = fp
    if receipt.structured is not None:
        receipt.structured["environment_fingerprint"] = dict(fp)
    return receipt


def sandbox_capability_summary(root: Path) -> dict[str, Any]:
    b = bubblewrap_probe()
    return {
        "bubblewrap": b,
        "full_sandbox_available": bool(b.get("available")),
        "recommended_untrusted_profile": "filesystem-contained" if b.get("available") else None,
        "capabilities": discover_capabilities(root),
    }

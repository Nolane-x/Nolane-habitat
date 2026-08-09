from __future__ import annotations

import atexit
import threading

_LOCK = threading.RLock()
_SHUTDOWN_COUNT = 0


def shutdown_runtime_services() -> dict:
    """Close process-shared optional runtime services deterministically.

    Workspace.close() remains the narrow cleanup boundary. This host-level boundary exists because
    compatibility callers from early Habitat releases were not required to close every workspace.
    Global services therefore must stay bounded and independently drainable.
    """
    global _SHUTDOWN_COUNT
    with _LOCK:
        closed: list[str] = []
        errors: list[dict[str, str]] = []
        try:
            from .semantic.ts_language_service import close_all_typescript_sessions
            close_all_typescript_sessions(); closed.append("typescript-language-services")
        except Exception as exc:  # shutdown is best-effort but observable
            errors.append({"service": "typescript-language-services", "error": f"{type(exc).__name__}: {exc}"})
        try:
            from .semantic.python_jedi import close_all_jedi_projects
            close_all_jedi_projects(); closed.append("jedi-project-cache")
        except Exception as exc:
            errors.append({"service": "jedi-project-cache", "error": f"{type(exc).__name__}: {exc}"})
        try:
            from .ui.browser_provider import _close_shared_browser
            _close_shared_browser(); closed.append("shared-browser-engine")
        except Exception as exc:
            errors.append({"service": "shared-browser-engine", "error": f"{type(exc).__name__}: {exc}"})
        _SHUTDOWN_COUNT += 1
        return {"closed": closed, "errors": errors, "idempotent": True, "shutdown_count": _SHUTDOWN_COUNT}


def runtime_service_status() -> dict:
    ts: dict
    jedi: dict
    browser: dict
    try:
        from .semantic import ts_language_service as mod
        ts = {"session_count": len(mod._sessions), "pids": [x.proc.pid for x in mod._sessions.values() if x.proc.poll() is None]}
    except Exception as exc:
        ts = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        from .semantic import python_jedi as mod
        with mod._PROJECT_LOCK:
            jedi = {"project_count": len(mod._PROJECTS), "max_projects": mod._MAX_PROJECTS}
    except Exception as exc:
        jedi = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        from .ui import browser_provider as mod
        browser = {"playwright_started": mod._SHARED_PW is not None, "browser_started": mod._SHARED_BROWSER is not None, "shared_users": mod._SHARED_USERS,
                   "continuous_cdp_enabled": mod._SHARED_DEBUG_PORT is not None, "raw_stream_count": len(mod._ACTIVE_RAW_STREAMS)}
    except Exception as exc:
        browser = {"error": f"{type(exc).__name__}: {exc}"}
    return {"typescript": ts, "jedi": jedi, "browser": browser}


atexit.register(shutdown_runtime_services)

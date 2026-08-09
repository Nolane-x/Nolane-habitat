from __future__ import annotations

import atexit
import base64
import contextlib
import hashlib
import json
import mimetypes
import os
import re
import shutil
import socket
import threading
import time
from dataclasses import dataclass, field
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlsplit, urlunsplit

from ..util import stable_id


_SHARED_LOCK = threading.RLock()
_SHARED_PW = None
_SHARED_BROWSER = None
_SHARED_USERS = 0
_SHARED_DEBUG_PORT = None
_SHARED_DEBUG_ORIGIN = None
_ACTIVE_RAW_STREAMS: set[Any] = set()


_SENSITIVE_KEY = re.compile(r"(?:pass(?:word|wd)?|secret|token|api[-_]?key|auth(?:orization)?|bearer|credential|session[-_]?key|cc[-_]?number|cvv|cvc)", re.I)
_SECRET_ASSIGNMENT = re.compile(r"(?i)([\"']?\b(?:password|passwd|secret|token|access[-_]?token|refresh[-_]?token|api[-_]?key|authorization|credential|cookie)\b[\"']?\s*[:=]\s*)([\"']?)([^\"'\s,;}\]]+)([\"']?)")
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_FRAME_RING = 6
_EVENT_BUFFER_LIMIT = 500


def frame_key_for_session(session_id: str) -> str:
    """Collision-resistant, Windows-safe key for ephemeral visual mirror files."""
    return hashlib.sha256(session_id.encode("utf-8", errors="strict")).hexdigest()[:32]


def _redact_observer_text(value: str) -> str:
    text = str(value)
    text = _BEARER_VALUE.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]{m.group(4)}", text)


def _sanitize_observer_url(value: str) -> str:
    """Keep navigation useful while removing common credential-bearing query/fragment values."""
    try:
        parts = urlsplit(str(value))
    except Exception:
        return _redact_observer_text(str(value))
    query = [(key, "[REDACTED]" if _SENSITIVE_KEY.search(key) else val)
             for key, val in parse_qsl(parts.query, keep_blank_values=True)]
    fragment = parts.fragment
    if "=" in fragment:
        fragment = urlencode([(key, "[REDACTED]" if _SENSITIVE_KEY.search(key) else val)
                              for key, val in parse_qsl(fragment, keep_blank_values=True)], doseq=True)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = "[REDACTED]@" + netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query, doseq=True), fragment))

def _close_shared_browser():
    global _SHARED_PW, _SHARED_BROWSER, _SHARED_USERS, _SHARED_DEBUG_PORT, _SHARED_DEBUG_ORIGIN
    with _SHARED_LOCK:
        for stream in list(_ACTIVE_RAW_STREAMS):
            with contextlib.suppress(Exception):
                stream.stop(timeout=0.8)
        _ACTIVE_RAW_STREAMS.clear()
        if _SHARED_BROWSER is not None:
            with contextlib.suppress(Exception): _SHARED_BROWSER.close()
            _SHARED_BROWSER = None
        if _SHARED_PW is not None:
            with contextlib.suppress(Exception): _SHARED_PW.stop()
            _SHARED_PW = None
        _SHARED_USERS = 0
        _SHARED_DEBUG_PORT = None
        _SHARED_DEBUG_ORIGIN = None

atexit.register(_close_shared_browser)


def _websocket_available() -> bool:
    try:
        import websocket  # noqa: F401
        return True
    except Exception:
        return False


def _choose_loopback_port() -> int:
    """Reserve-then-release a loopback port for Chromium DevTools.

    There is a small TOCTOU window after close; launch handles collision by falling back to
    Playwright-only mode rather than widening the bind address or retrying unsafely.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _RawCDPScreencast:
    """Continuous CDP frame receiver that never touches Playwright from its worker thread."""

    def __init__(self, *, ws_url: str, origin: str, width: int, height: int, on_frame, on_error):
        self.ws_url = ws_url
        self.origin = origin
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.on_frame = on_frame
        self.on_error = on_error
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws = None
        self._command_id = 1
        self.error: str | None = None
        self.started = False

    def _next_id(self) -> int:
        value = self._command_id
        self._command_id += 1
        return value

    @staticmethod
    def _message(ws, method: str, params: dict | None = None, *, command_id: int) -> None:
        ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}, separators=(",", ":")))

    def start(self, timeout: float = 1.8) -> bool:
        self._thread = threading.Thread(target=self._run, name="habitat-cdp-screencast", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=max(0.05, timeout))
        if not self.started:
            self.stop(timeout=0.8)
        return self.started

    def _run(self) -> None:
        try:
            import websocket
            last_exc = None
            for attempt in range(12):
                if self._stop.is_set():
                    return
                try:
                    self._ws = websocket.create_connection(
                        self.ws_url,
                        timeout=0.35,
                        origin=self.origin,
                        http_no_proxy=["127.0.0.1", "localhost"],
                        enable_multithread=True,
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    time.sleep(min(0.03 * (attempt + 1), 0.15))
            if self._ws is None:
                raise RuntimeError(f"DevTools websocket unavailable: {last_exc}")

            start_id = self._next_id()
            self._message(self._ws, "Page.startScreencast", {
                "format": "png",
                "maxWidth": self.width,
                "maxHeight": self.height,
                "everyNthFrame": 1,
            }, command_id=start_id)

            while not self._stop.is_set():
                try:
                    raw = self._ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if raw is None:
                    raise RuntimeError("DevTools websocket closed before stream stop")
                payload = json.loads(raw)
                if payload.get("id") == start_id:
                    if payload.get("error"):
                        raise RuntimeError(f"Page.startScreencast failed: {payload['error']}")
                    self.started = True
                    self._ready.set()
                    continue
                if payload.get("method") != "Page.screencastFrame":
                    continue
                params = payload.get("params") or {}
                session_id = params.get("sessionId")
                try:
                    data = base64.b64decode(str(params.get("data") or ""), validate=True)
                    self.on_frame(data)
                finally:
                    if session_id is not None and self._ws is not None:
                        ack_id = self._next_id()
                        self._message(self._ws, "Page.screencastFrameAck", {"sessionId": int(session_id)}, command_id=ack_id)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"[:300]
            if not self._stop.is_set():
                with contextlib.suppress(Exception):
                    self.on_error(self.error)
        finally:
            self._ready.set()
            ws = self._ws
            if ws is not None:
                if self.started and not self._stop.is_set():
                    with contextlib.suppress(Exception):
                        self._message(ws, "Page.stopScreencast", command_id=self._next_id())
                with contextlib.suppress(Exception):
                    ws.close()
            self._ws = None
            self.started = False

    def stop(self, timeout: float = 1.2) -> None:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=max(0.05, timeout))
        if thread.is_alive():
            ws = self._ws
            if ws is not None:
                with contextlib.suppress(Exception):
                    ws.close()
            thread.join(timeout=0.5)
        self._thread = None



class BrowserUnavailable(RuntimeError):
    pass


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@dataclass
class _Session:
    id: str
    page: Any
    target: str
    target_path: str | None
    console: list[dict] = field(default_factory=list)
    network: list[dict] = field(default_factory=list)
    previous: dict[str, dict] = field(default_factory=dict)
    frame_seq: int = 0
    last_frame_path: str | None = None
    last_frame_at: float | None = None
    last_frame_source: str | None = None
    frame_lock: Any = field(default_factory=threading.RLock)
    cdp: Any = None
    raw_stream: Any = None
    stream_epoch: str | None = None
    stream_active: bool = False
    stream_mode: str = "snapshot-fallback"
    stream_seq: int = 0
    stream_started_at: float | None = None
    stream_error: str | None = None
    stream_ack_errors: int = 0
    console_dropped: int = 0
    network_dropped: int = 0
    closed: bool = False


class BrowserRuntime:
    def __init__(self, root: Path, artifact_dir: Path):
        self.root = root.resolve()
        self.artifact_dir = artifact_dir.resolve()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        # Observer mirror pixels are ephemeral, not release evidence. Remove crash-left live frames
        # before a new runtime starts so sensitive UI pixels are not silently retained forever.
        live_dir = self.artifact_dir / "live"
        if live_dir.is_dir():
            for stale in live_dir.iterdir():
                if stale.is_file():
                    with contextlib.suppress(OSError):
                        stale.unlink()
        self._pw = None
        self._browser = None
        self._sessions: dict[str, _Session] = {}
        self._httpd = None
        self._http_thread = None
        self._origin = None
        self._shared_acquired = False

    @staticmethod
    def probe() -> dict:
        try:
            import playwright.sync_api  # noqa: F401
        except Exception as exc:
            return {"available": False, "reason": f"Playwright import failed: {exc}", "browser": None}
        browser = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        if not browser:
            return {"available": False, "reason": "no Chromium/Chrome executable found", "browser": None}
        sandbox_enabled = not (hasattr(os, "geteuid") and os.geteuid() == 0)
        return {"available": True, "reason": "Playwright + system Chromium available", "browser": browser,
                "browser_sandbox_enabled": sandbox_enabled,
                "continuous_stream_transport_available": _websocket_available(),
                "security_note": None if sandbox_enabled else "running as root requires Chromium --no-sandbox; treat UI execution as trusted-project only"}

    def _ensure_browser(self):
        global _SHARED_PW, _SHARED_BROWSER, _SHARED_USERS, _SHARED_DEBUG_PORT, _SHARED_DEBUG_ORIGIN
        if self._browser is not None:
            return
        probe = self.probe()
        if not probe["available"]:
            raise BrowserUnavailable(probe["reason"])
        from playwright.sync_api import sync_playwright
        with _SHARED_LOCK:
            if _SHARED_BROWSER is None:
                _SHARED_PW = sync_playwright().start()
                try:
                    base_args = ["--disable-dev-shm-usage"]
                    if not probe.get("browser_sandbox_enabled", True):
                        base_args.insert(0, "--no-sandbox")
                    debug_port = None
                    debug_origin = None
                    launch_args = list(base_args)
                    if _websocket_available():
                        debug_port = _choose_loopback_port()
                        debug_origin = f"http://127.0.0.1:{debug_port}"
                        launch_args.extend([
                            "--remote-debugging-address=127.0.0.1",
                            f"--remote-debugging-port={debug_port}",
                            f"--remote-allow-origins={debug_origin}",
                        ])
                    try:
                        _SHARED_BROWSER = _SHARED_PW.chromium.launch(
                            headless=True, executable_path=probe["browser"], args=launch_args
                        )
                        _SHARED_DEBUG_PORT = debug_port
                        _SHARED_DEBUG_ORIGIN = debug_origin
                    except Exception:
                        # Continuous transport is optional. If the loopback debug endpoint cannot
                        # be established (for example a port race or enterprise Chromium policy),
                        # preserve the semantic runtime and fall back to Playwright's CDP session.
                        if debug_port is None:
                            raise
                        _SHARED_BROWSER = _SHARED_PW.chromium.launch(
                            headless=True, executable_path=probe["browser"], args=base_args
                        )
                        _SHARED_DEBUG_PORT = None
                        _SHARED_DEBUG_ORIGIN = None
                except Exception:
                    with contextlib.suppress(Exception): _SHARED_PW.stop()
                    _SHARED_PW = None
                    _SHARED_DEBUG_PORT = None
                    _SHARED_DEBUG_ORIGIN = None
                    raise
            self._pw = _SHARED_PW
            self._browser = _SHARED_BROWSER
            if not self._shared_acquired:
                _SHARED_USERS += 1
                self._shared_acquired = True

    def _ensure_http_server(self) -> str:
        if self._origin:
            return self._origin
        handler = partial(_QuietHandler, directory=str(self.root))
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = self._httpd.server_address[1]
        self._http_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._http_thread.start()
        self._origin = f"http://127.0.0.1:{port}"
        return self._origin

    def _resolve_project_target(self, target: str) -> tuple[Path, str]:
        path = (self.root / target).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("UI target escapes source root")
        if not path.is_file():
            raise FileNotFoundError(target)
        return path, path.relative_to(self.root).as_posix()

    def _install_project_route(self, page):
        def handler(route):
            parsed = urlparse(route.request.url)
            rel = unquote(parsed.path.lstrip("/"))
            path = (self.root / rel).resolve()
            if path != self.root and self.root not in path.parents:
                route.abort(); return
            if not path.is_file():
                route.fulfill(status=404, body=b"not found"); return
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            route.fulfill(status=200, body=path.read_bytes(), content_type=ctype)
        page.route("http://habitat.local/**", handler)

    def _install_network_policy(self, page, *, allow_external: bool = False):
        """Default-deny project networking and never expose Habitat's DevTools control port."""
        def guard(route):
            parsed = urlparse(route.request.url)
            host = (parsed.hostname or "").lower()
            scheme = parsed.scheme.lower()
            # Continuous observer streaming uses a privileged loopback DevTools endpoint. Project
            # JavaScript must never reach it, even when the caller explicitly allows external web
            # traffic. Exact-origin CDP checks are defense-in-depth, not the only boundary.
            if (_SHARED_DEBUG_PORT is not None and host in {"127.0.0.1", "localhost"}
                    and parsed.port == int(_SHARED_DEBUG_PORT)):
                route.abort("blockedbyclient"); return
            if allow_external or host in {"habitat.local", "127.0.0.1", "localhost"} or scheme in {"data", "blob", "about"}:
                route.fallback(); return
            route.abort("blockedbyclient")
        page.route("**/*", guard)

    def _set_project_content(self, page, path: Path, rel: str):
        self._install_project_route(page)
        html = path.read_text(encoding="utf-8", errors="replace")
        parent = Path(rel).parent.as_posix()
        base = "http://habitat.local/" + ((parent.rstrip("/") + "/") if parent not in {".", ""} else "")
        base_tag = f'<base href="{base}">'
        instrumentation = r"""<script data-nolane-habitat-instrumentation>
(() => {
  try {
    const map = new WeakMap();
    Object.defineProperty(window, '__nolaneHabitatListenerMap', {value: map, configurable: false});
    const original = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function(type, listener, options) {
      try {
        const existing = map.get(this) || [];
        const stack = (new Error('nolane-listener-registration')).stack || '';
        existing.push({type: String(type), stack: stack.slice(0, 5000)});
        map.set(this, existing.slice(-30));
      } catch (_) {}
      return original.call(this, type, listener, options);
    };
  } catch (_) {}
})();
</script>"""
        lower = html.lower()
        injected = base_tag + instrumentation
        if "<head" in lower:
            idx = lower.find(">", lower.find("<head"))
            html = html[:idx+1] + injected + html[idx+1:]
        else:
            html = injected + html
        page.set_content(html, wait_until="domcontentloaded", timeout=15_000)

    @staticmethod
    def _normalize_viewport(viewport: dict | None) -> dict:
        if viewport is None:
            return {"width": 1440, "height": 900}
        if not isinstance(viewport, dict):
            raise TypeError("viewport must be an object with integer width/height")
        unknown = set(viewport) - {"width", "height"}
        if unknown:
            raise ValueError(f"unsupported viewport fields: {', '.join(sorted(map(str, unknown)))}")
        out = {}
        for key in ("width", "height"):
            value = viewport.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 16_384:
                raise ValueError(f"viewport.{key} must be an integer in [1,16384]")
            out[key] = int(value)
        return out

    def open(self, target: str, *, viewport: dict | None = None, screenshot: bool = False, allow_external: bool = False) -> dict:
        normalized_viewport = self._normalize_viewport(viewport)
        self._ensure_browser()
        target_path = None
        context = None
        sess = None
        sid = stable_id("ui-session", target, str(time.time_ns()))
        try:
            context = self._browser.new_context(viewport=normalized_viewport)
            page = context.new_page()
            sess = _Session(sid, page, target, None)
            self._install_network_policy(page, allow_external=allow_external)
            def append_console(msg):
                if len(sess.console) >= _EVENT_BUFFER_LIMIT:
                    del sess.console[:max(1, len(sess.console) - _EVENT_BUFFER_LIMIT + 1)]
                    sess.console_dropped += 1
                sess.console.append({"type": msg.type, "text": _redact_observer_text(msg.text)[:2000]})

            def append_network(response):
                if len(sess.network) >= _EVENT_BUFFER_LIMIT:
                    del sess.network[:max(1, len(sess.network) - _EVENT_BUFFER_LIMIT + 1)]
                    sess.network_dropped += 1
                sess.network.append({"method": response.request.method, "url": _sanitize_observer_url(response.url), "status": response.status})

            page.on("console", append_console)
            page.on("response", append_network)
            if target.startswith("http://") or target.startswith("https://"):
                parsed = urlparse(target)
                if not allow_external and (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost"}:
                    raise PermissionError("external UI navigation is denied by default; set allow_external=true explicitly")
                page.goto(target, wait_until="domcontentloaded", timeout=15_000)
            else:
                path, target_path = self._resolve_project_target(target)
                sess.target_path = target_path
                self._set_project_content(page, path, target_path)
            self._sessions[sid] = sess
            obs = self.observe(sid, screenshot=screenshot)
            self._start_screencast(sess)
            if sess.stream_mode == "cdp-screencast-cooperative":
                # Cooperative fallback dispatches CDP callbacks only while the owning sync loop is
                # pumped. The websocket-live transport does not need or use this pump.
                with contextlib.suppress(Exception):
                    page.wait_for_timeout(70)
            obs.update(self._frame_public_state(sess))
            obs["opened"] = True
            probe = self.probe()
            obs["security"] = {"external_network_allowed": bool(allow_external),
                               "browser_sandbox_enabled": bool(probe.get("browser_sandbox_enabled", False)),
                               "loopback_devtools_enabled": _SHARED_DEBUG_PORT is not None,
                               "loopback_devtools_scope": "127.0.0.1 only" if _SHARED_DEBUG_PORT is not None else None,
                               "project_access_to_devtools": "denied" if _SHARED_DEBUG_PORT is not None else "not-applicable",
                               "security_note": probe.get("security_note")}
            return obs
        except Exception:
            self._sessions.pop(sid, None)
            if sess is not None:
                sess.closed = True
                self._stop_screencast(sess)
            if context is not None:
                with contextlib.suppress(Exception):
                    context.close()
            if sess is not None:
                self._cleanup_stream_artifacts(sess)
            raise

    def _extract_elements(self, page) -> list[dict]:
        elements = page.evaluate(r'''() => {
          window.__nolaneHabitatCounter = window.__nolaneHabitatCounter || 0;
          window.__nolaneHabitatElementHandles = window.__nolaneHabitatElementHandles || new WeakMap();
          const selector = 'a,button,input,textarea,select,option,form,label,h1,h2,h3,h4,h5,h6,img,nav,main,section,article,[role],[aria-label],[id],[data-testid]';
          const els = Array.from(document.querySelectorAll(selector)).slice(0, 1500);
          const claimed = new Set();
          const safePart = (value) => encodeURIComponent(String(value));
          const allocateHandle = (el) => {
            let h = window.__nolaneHabitatElementHandles.get(el);
            if (h && !claimed.has(h)) { claimed.add(h); el.setAttribute('data-nolane-habitat-handle', h); return h; }
            const id = el.id; const testid = el.getAttribute('data-testid');
            const base = id ? 'ui:id:' + safePart(id) : testid ? 'ui:testid:' + safePart(testid) : 'ui:auto';
            h = base;
            if (claimed.has(h)) h = base + '~' + (++window.__nolaneHabitatCounter);
            else if (base === 'ui:auto') h = base + ':' + (++window.__nolaneHabitatCounter);
            while (claimed.has(h)) h = base + '~' + (++window.__nolaneHabitatCounter);
            window.__nolaneHabitatElementHandles.set(el, h); claimed.add(h);
            // Never trust a project-supplied handle attribute as runtime identity.
            el.setAttribute('data-nolane-habitat-handle', h);
            return h;
          };
          const roleOf = (el) => {
            const explicit = el.getAttribute('role'); if (explicit) return explicit;
            const t = el.tagName.toLowerCase();
            if (t === 'button') return 'button'; if (t === 'a' && el.hasAttribute('href')) return 'link';
            if (t === 'textarea') return 'textbox'; if (t === 'select') return 'combobox'; if (t === 'form') return 'form';
            if (/^h[1-6]$/.test(t)) return 'heading'; if (t === 'nav') return 'navigation'; if (t === 'main') return 'main';
            if (t === 'img') return 'img';
            if (t === 'input') { const ty=(el.getAttribute('type')||'text').toLowerCase(); return ty==='checkbox'?'checkbox':ty==='radio'?'radio':ty==='submit'?'button':'textbox'; }
            return 'generic';
          };
          const nameOf = (el) => {
            const aria = el.getAttribute('aria-label'); if (aria) return aria.trim();
            if (el.labels && el.labels.length) return Array.from(el.labels).map(x=>x.innerText.trim()).filter(Boolean).join(' ');
            for (const k of ['placeholder','alt','title']) { const v=el.getAttribute(k); if(v) return v.trim(); }
            const txt=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim(); return txt.slice(0,300)||null;
          };
          const sensitiveValue = (el) => {
            const attrs=['id','name','type','aria-label','placeholder','autocomplete'].map(k=>String(el.getAttribute(k)||'').toLowerCase()).join(' ');
            return String(el.getAttribute('type')||'').toLowerCase()==='password' || /password|passwd|secret|token|api[-_]?key|credit-card|cc-number|cc-csc|cvv|cvc|credential/.test(attrs);
          };
          return els.map(el => {
            const h=allocateHandle(el);
            const r=el.getBoundingClientRect(), cs=getComputedStyle(el);
            const attrs={}; for(const k of ['id','name','class','type','href','role','aria-label','placeholder','data-testid']){ const v=el.getAttribute(k); if(v!==null) attrs[k]=v; }
            const visible = cs.display!=='none' && cs.visibility!=='hidden' && parseFloat(cs.opacity||'1')>0 && r.width>0 && r.height>0;
            const listenerEvidence = (window.__nolaneHabitatListenerMap && window.__nolaneHabitatListenerMap.get(el) || []).map(x => ({type:x.type, stack:x.stack}));
            const inlineHandlers = {}; for (const a of Array.from(el.attributes || [])) { if (a.name && a.name.toLowerCase().startsWith('on')) inlineHandlers[a.name.toLowerCase()] = String(a.value||'').slice(0,1000); }
            return {handle:h, tag:el.tagName.toLowerCase(), role:roleOf(el), name:nameOf(el),
              text:(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim().slice(0,500), attrs,
              visible, enabled:!el.disabled,
              value:(() => { if(!('value' in el)) return null; const v=String(el.value); return sensitiveValue(el) && v ? '[REDACTED]' : v.slice(0,500); })(),
              value_redacted:sensitiveValue(el),
              checked:('checked' in el ? !!el.checked : null),
              rect:{x:Math.round(r.x*10)/10,y:Math.round(r.y*10)/10,width:Math.round(r.width*10)/10,height:Math.round(r.height*10)/10},
              style:{display:cs.display,visibility:cs.visibility,position:cs.position,overflowX:cs.overflowX,overflowY:cs.overflowY},
              listener_evidence:listenerEvidence, inline_handlers:inlineHandlers
            };
          });
        }''')
        for element in elements:
            for field in ("name", "text"):
                if element.get(field) is not None:
                    element[field] = _redact_observer_text(str(element[field]))
            attrs = element.get("attrs") or {}
            for key, value in list(attrs.items()):
                if value is None:
                    continue
                attrs[key] = _sanitize_observer_url(str(value)) if key == "href" else _redact_observer_text(str(value))
            handlers = element.get("inline_handlers") or {}
            for key, value in list(handlers.items()):
                handlers[key] = _redact_observer_text(value)
            for listener in element.get("listener_evidence") or []:
                if listener.get("stack") is not None:
                    listener["stack"] = _redact_observer_text(str(listener["stack"]))
        return elements

    def _redact_aria_snapshot(self, page, aria: str) -> str:
        """Remove sensitive control values and credential-bearing URLs from ARIA text."""
        try:
            sensitive_values = page.evaluate("""() => {
              const out=[];
              for(const el of document.querySelectorAll('input,textarea,select')){
                const attrs=['id','name','type','aria-label','placeholder','autocomplete'].map(k=>String(el.getAttribute(k)||'').toLowerCase()).join(' ');
                const sensitive=String(el.getAttribute('type')||'').toLowerCase()==='password' || /password|passwd|secret|token|api[-_]?key|credit-card|cc-number|cc-csc|cvv|cvc|credential/.test(attrs);
                if(sensitive && 'value' in el && String(el.value)) out.push(String(el.value));
              }
              return out.slice(0,100);
            }""")
        except Exception:
            sensitive_values = []
        clean = str(aria)
        for value in sorted({str(v) for v in sensitive_values if v}, key=len, reverse=True):
            clean = clean.replace(value, "[REDACTED]")
        lines=[]
        for line in clean.splitlines():
            marker="/url:"
            if marker in line:
                head, raw = line.split(marker, 1)
                line = head + marker + " " + _sanitize_observer_url(raw.strip())
            lines.append(line)
        return "\n".join(lines)

    def _layout_diagnostics(self, page) -> list[dict]:
        return page.evaluate(r'''() => {
          const out=[]; const vw=innerWidth, vh=innerHeight;
          const els=Array.from(document.querySelectorAll('[data-nolane-habitat-handle]')).slice(0,800);
          for(const el of els){
            const h=el.getAttribute('data-nolane-habitat-handle'), r=el.getBoundingClientRect();
            if(el.clientWidth>0 && el.scrollWidth>el.clientWidth+2) out.push({kind:'horizontal-overflow',handle:h,delta:el.scrollWidth-el.clientWidth});
            if(r.width>0 && r.height>0 && (r.left < -1 || r.right > vw+1 || r.top < -1 || r.bottom > vh+1)) out.push({kind:'viewport-clipping',handle:h,rect:{x:r.x,y:r.y,width:r.width,height:r.height}});
            if(out.length>=100) break;
          }
          return out;
        }''')

    def _live_dir(self) -> Path:
        live_dir = self.artifact_dir / "live"
        live_dir.mkdir(parents=True, exist_ok=True)
        return live_dir

    def _frame_public_state(self, sess: _Session) -> dict:
        # Frame and stream fields are updated by the raw CDP worker. Read them under the same
        # per-session lock so callers never observe a mixed seq/path/source tuple.
        with sess.frame_lock:
            active = bool(sess.stream_active and not sess.closed)
            return {
                "observer_frame_path": sess.last_frame_path,
                "observer_frame_seq": sess.frame_seq,
                "observer_frame_at": sess.last_frame_at,
                "observer_frame_source": sess.last_frame_source,
                "observer_stream": {
                    "mode": sess.stream_mode,
                    "active": active,
                    "epoch": sess.stream_epoch,
                    "seq": sess.stream_seq,
                    "started_at": sess.stream_started_at,
                    "last_frame_at": sess.last_frame_at,
                    "error": sess.stream_error,
                    "ack_errors": sess.stream_ack_errors,
                    "poll_hint_ms": 55 if sess.stream_mode == "cdp-websocket-live" and active else (90 if active else 350),
                    "frame_retention": _FRAME_RING,
                },
            }

    def _write_stream_meta(self, sess: _Session, *, status: str = "live") -> None:
        live_dir = self._live_dir()
        key = frame_key_for_session(sess.id)
        final = live_dir / f"{key}-stream.json"
        tmp = live_dir / f".{key}-stream-{time.time_ns()}.tmp"
        with sess.frame_lock:
            payload = {
                "session_id": sess.id,
                "status": status,
                "frame_seq": sess.frame_seq,
                "stream_seq": sess.stream_seq,
                "stream_epoch": sess.stream_epoch,
                "stream_mode": sess.stream_mode,
                "stream_active": bool(sess.stream_active and not sess.closed),
                "frame_at": sess.last_frame_at,
                "frame_source": sess.last_frame_source,
                "frame_file": Path(sess.last_frame_path).name if sess.last_frame_path else None,
                "poll_hint_ms": 55 if sess.stream_mode == "cdp-websocket-live" and sess.stream_active else (90 if sess.stream_active else 350),
            }
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, final)
        finally:
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()

    def _write_observer_frame_bytes(self, sess: _Session, data: bytes, *, source: str) -> dict:
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("observer frame must be PNG")
        with sess.frame_lock:
            if sess.closed:
                return self._frame_public_state(sess)
            sess.frame_seq += 1
            if source.startswith("cdp-"):
                sess.stream_seq += 1
            seq = sess.frame_seq
            live_dir = self._live_dir()
            key = frame_key_for_session(sess.id)
            final = live_dir / f"{key}-frame-{seq:09d}.png"
            tmp = live_dir / f".{key}-frame-{seq:09d}-{time.time_ns()}.tmp"
            try:
                tmp.write_bytes(data)
                os.replace(tmp, final)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    tmp.unlink()
            sess.last_frame_path = str(final)
            sess.last_frame_at = time.time()
            sess.last_frame_source = source
            self._write_stream_meta(sess)
            # Versioned ring avoids Windows replace/read races while bounding ephemeral pixels.
            cutoff = seq - _FRAME_RING
            if cutoff > 0:
                old = live_dir / f"{key}-frame-{cutoff:09d}.png"
                with contextlib.suppress(FileNotFoundError, PermissionError):
                    old.unlink()
            return self._frame_public_state(sess)

    def _capture_observer_frame(self, sess: _Session) -> dict:
        """Capture a fallback visual frame; pixels remain human-observer-only, never a verifier."""
        data = sess.page.screenshot(type="png", full_page=False)
        return self._write_observer_frame_bytes(sess, data, source="snapshot-fallback")

    def _ensure_observer_frame(self, sess: _Session, *, max_age_s: float = 0.18) -> dict:
        # A continuous websocket stream owns frame freshness independently of Playwright calls.
        # Do not overwrite a valid live frame with a synchronous snapshot merely because the
        # semantic observation happens between animation frames.
        if sess.stream_mode == "cdp-websocket-live" and sess.stream_seq > 0 and sess.last_frame_path:
            return self._frame_public_state(sess)
        if sess.last_frame_path and sess.last_frame_at and sess.stream_active and time.time() - sess.last_frame_at <= max_age_s:
            return self._frame_public_state(sess)
        return self._capture_observer_frame(sess)

    def _start_screencast(self, sess: _Session) -> dict:
        """Start the strongest safe CDP visual transport available.

        Preferred mode is a raw loopback DevTools WebSocket. Its worker owns only that socket and
        atomically publishes PNG artifacts, so frames continue while the main sync Playwright
        thread is idle. If unavailable, Habitat falls back to an owning-thread Playwright CDP
        screencast and finally to explicit snapshots.
        """
        global _SHARED_DEBUG_PORT, _SHARED_DEBUG_ORIGIN
        sess.stream_epoch = stable_id("ui-stream", sess.id, str(time.time_ns()))
        sess.stream_started_at = time.time()
        viewport = sess.page.viewport_size or {"width": 1440, "height": 900}

        # Strongest mode: independent loopback CDP websocket. Obtain target identity once on the
        # owning Playwright thread, then detach before the background socket starts.
        if _SHARED_DEBUG_PORT and _SHARED_DEBUG_ORIGIN and _websocket_available():
            identity_cdp = None
            try:
                identity_cdp = sess.page.context.new_cdp_session(sess.page)
                info = identity_cdp.send("Target.getTargetInfo") or {}
                target_id = ((info.get("targetInfo") or {}).get("targetId") or "").strip()
                if not target_id:
                    raise RuntimeError("CDP target id unavailable")
                identity_cdp.detach(); identity_cdp = None

                def on_error(message: str) -> None:
                    with sess.frame_lock:
                        sess.stream_error = str(message)[:300]
                        sess.stream_active = False
                    with contextlib.suppress(Exception):
                        self._write_stream_meta(sess, status="degraded")

                raw = _RawCDPScreencast(
                    ws_url=f"ws://127.0.0.1:{int(_SHARED_DEBUG_PORT)}/devtools/page/{target_id}",
                    origin=str(_SHARED_DEBUG_ORIGIN),
                    width=int(viewport.get("width") or 1440),
                    height=int(viewport.get("height") or 900),
                    on_frame=lambda data: self._write_observer_frame_bytes(sess, data, source="cdp-websocket-live"),
                    on_error=on_error,
                )
                if raw.start():
                    sess.raw_stream = raw
                    with _SHARED_LOCK:
                        _ACTIVE_RAW_STREAMS.add(raw)
                    sess.stream_mode = "cdp-websocket-live"
                    sess.stream_active = True
                    sess.stream_error = None
                    self._write_stream_meta(sess)
                    return self._frame_public_state(sess)
                sess.stream_error = f"continuous CDP unavailable: {raw.error or 'stream did not become ready'}"[:300]
            except Exception as exc:
                sess.stream_error = f"continuous CDP unavailable: {type(exc).__name__}: {exc}"[:300]
            finally:
                if identity_cdp is not None:
                    with contextlib.suppress(Exception):
                        identity_cdp.detach()

        # Compatible mode: callbacks dispatch only while sync Playwright's owning loop is pumped.
        try:
            cdp = sess.page.context.new_cdp_session(sess.page)
            sess.cdp = cdp
            sess.stream_mode = "cdp-screencast-cooperative"
            sess.stream_active = True

            def on_frame(payload):
                sid = payload.get("sessionId") if isinstance(payload, dict) else None
                try:
                    if not sess.closed and sess.stream_active:
                        raw = base64.b64decode(str(payload.get("data") or ""), validate=True)
                        self._write_observer_frame_bytes(sess, raw, source="cdp-screencast-cooperative")
                except Exception as exc:
                    sess.stream_error = f"{type(exc).__name__}: {exc}"[:300]
                    with contextlib.suppress(Exception):
                        self._write_stream_meta(sess, status="degraded")
                finally:
                    if sid is not None and sess.cdp is not None:
                        try:
                            sess.cdp.send("Page.screencastFrameAck", {"sessionId": int(sid)})
                        except Exception:
                            sess.stream_ack_errors += 1

            cdp.on("Page.screencastFrame", on_frame)
            cdp.send("Page.startScreencast", {
                "format": "png",
                "maxWidth": int(viewport.get("width") or 1440),
                "maxHeight": int(viewport.get("height") or 900),
                "everyNthFrame": 2,
            })
            self._write_stream_meta(sess)
        except Exception as exc:
            sess.stream_active = False
            sess.stream_mode = "snapshot-fallback"
            prior = (sess.stream_error + "; ") if sess.stream_error else ""
            sess.stream_error = (prior + f"Playwright CDP unavailable: {type(exc).__name__}: {exc}")[:300]
            if sess.cdp is not None:
                with contextlib.suppress(Exception):
                    sess.cdp.detach()
                sess.cdp = None
            with contextlib.suppress(Exception):
                self._write_stream_meta(sess, status="degraded")
        return self._frame_public_state(sess)

    def _stop_screencast(self, sess: _Session) -> None:
        sess.stream_active = False
        if sess.raw_stream is not None:
            raw = sess.raw_stream
            with contextlib.suppress(Exception):
                raw.stop()
            with _SHARED_LOCK:
                _ACTIVE_RAW_STREAMS.discard(raw)
            sess.raw_stream = None
        if sess.cdp is not None:
            with contextlib.suppress(Exception):
                sess.cdp.send("Page.stopScreencast")
            with contextlib.suppress(Exception):
                sess.cdp.detach()
            sess.cdp = None

    def _cleanup_stream_artifacts(self, sess: _Session) -> None:
        live_dir = self._live_dir()
        key = frame_key_for_session(sess.id)
        for path in live_dir.glob(f"{key}-frame-*.png"):
            with contextlib.suppress(FileNotFoundError, PermissionError):
                path.unlink()
        meta = live_dir / f"{key}-stream.json"
        with contextlib.suppress(FileNotFoundError, PermissionError):
            meta.unlink()
        sess.last_frame_path = None

    def preview_action(self, session_id: str, action: str, handle: str, value: str | None = None) -> dict:
        """Describe the real target geometry before an action, without exposing sensitive values."""
        if value is not None and not isinstance(value, str):
            raise TypeError("UI action value must be a string or null")
        sess = self._sessions.get(session_id)
        if not sess:
            raise KeyError(session_id)
        locator = sess.page.locator(f'[data-nolane-habitat-handle="{handle}"]')
        if locator.count() != 1:
            raise ValueError(f"semantic handle must resolve to exactly one runtime element: {handle}")
        locator.scroll_into_view_if_needed(timeout=5_000)
        meta = locator.evaluate(r"""el => {
          const attrs={}; for(const k of ['id','name','type','role','aria-label','placeholder','autocomplete','data-testid']){const v=el.getAttribute(k);if(v!==null)attrs[k]=v}
          const role=el.getAttribute('role') || (el.tagName.toLowerCase()==='button'?'button':el.tagName.toLowerCase()==='a'?'link':(['input','textarea'].includes(el.tagName.toLowerCase())?'textbox':'generic'));
          const name=el.getAttribute('aria-label') || el.getAttribute('placeholder') || (el.innerText||el.textContent||'').replace(/\s+/g,' ').trim().slice(0,180) || null;
          return {tag:el.tagName.toLowerCase(),role,name,attrs};
        }""")
        box = locator.bounding_box()
        viewport = sess.page.viewport_size or {"width": 1440, "height": 900}
        if box:
            x = max(0.0, min(float(viewport["width"]), float(box["x"] + box["width"] / 2)))
            y = max(0.0, min(float(viewport["height"]), float(box["y"] + box["height"] / 2)))
            rect = {k: round(float(box[k]), 2) for k in ("x", "y", "width", "height")}
        else:
            x, y, rect = float(viewport["width"]) / 2, float(viewport["height"]) / 2, None
        attrs = meta.get("attrs") or {}
        for key, raw in list(attrs.items()):
            if raw is not None:
                attrs[key] = _redact_observer_text(str(raw))
        if meta.get("name") is not None:
            meta["name"] = _redact_observer_text(str(meta["name"]))
        sensitivity_blob = " ".join(str(attrs.get(k) or "") for k in ("id","name","type","aria-label","placeholder","autocomplete")).lower()
        sensitive = (str(attrs.get("type") or "").lower() == "password" or
                     any(token in sensitivity_blob for token in ("password","passwd","secret","token","api-key","api_key","credit-card","cc-number","cc-csc","cvv","cvc")))
        preview = None
        if value is not None:
            preview = "[REDACTED]" if sensitive else str(value)[:180]
        return {
            "action": action, "handle": handle,
            "target": {**meta, "rect": rect},
            "pointer": {"x": round(x,2), "y": round(y,2), "nx": round(x/max(1,float(viewport["width"])),6), "ny": round(y/max(1,float(viewport["height"])),6)},
            "viewport": viewport, "value_preview": preview, "value_length": (None if sensitive else (len(str(value)) if value is not None else 0)),
            "value_redacted": bool(value is not None and sensitive),
        }

    @staticmethod
    def _delta(previous: dict[str, dict], elements: list[dict]) -> dict:
        current = {e["handle"]: e for e in elements}
        added = [current[h] for h in current.keys() - previous.keys()]
        removed = [previous[h] for h in previous.keys() - current.keys()]
        changed = []
        keys = ("role", "name", "text", "visible", "enabled", "value", "checked", "rect")
        for h in current.keys() & previous.keys():
            before, after = previous[h], current[h]
            diff = {k: {"before": before.get(k), "after": after.get(k)} for k in keys if before.get(k) != after.get(k)}
            if diff:
                changed.append({"handle": h, "changes": diff})
        return {"added": added[:100], "removed": removed[:100], "changed": changed[:100]}

    def observe(self, session_id: str, *, screenshot: bool = False) -> dict:
        sess = self._sessions.get(session_id)
        if not sess:
            raise KeyError(session_id)
        page = sess.page
        elements = self._extract_elements(page)
        current = {e["handle"]: e for e in elements}
        delta = self._delta(sess.previous, elements) if sess.previous else {"added": [], "removed": [], "changed": []}
        sess.previous = current
        try:
            aria = page.locator("body").aria_snapshot(timeout=3000)
            aria = self._redact_aria_snapshot(page, aria)
        except Exception as exc:
            aria = f"<aria snapshot unavailable: {type(exc).__name__}>"
        screenshot_path = None
        if screenshot:
            safe_session_id = frame_key_for_session(session_id)
            screenshot_path = self.artifact_dir / f"{safe_session_id}-{time.time_ns()}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
        console = sess.console[-100:]; network = sess.network[-100:]
        dropped = {"console": int(sess.console_dropped), "network": int(sess.network_dropped)}
        sess.console.clear(); sess.network.clear(); sess.console_dropped = 0; sess.network_dropped = 0
        observer_frame = self._ensure_observer_frame(sess)
        return {
            "session_id": session_id,
            "mode": "runtime-browser-semantic",
            "target": _sanitize_observer_url(sess.target) if sess.target.startswith(("http://", "https://")) else sess.target,
            "target_path": sess.target_path,
            "url": _sanitize_observer_url(page.url),
            "title": _redact_observer_text(page.title()),
            "viewport": page.viewport_size,
            "elements": elements,
            "aria_snapshot": aria[:20_000],
            "layout_diagnostics": self._layout_diagnostics(page),
            "events": {"console": console, "network": network, "dropped": dropped},
            "delta": delta,
            "screenshot_path": str(screenshot_path) if screenshot_path else None,
            **observer_frame,
            "limitations": [
                "DOM/accessibility/layout are runtime observations, not proof of visual quality.",
                "Explicit screenshots are a secondary oracle and are captured only when requested.",
                "The Observatory operator frame is a human visual mirror only and is never used as a verification oracle.",
                "Continuous CDP video is observer-only; semantic/runtime evidence remains the correctness oracle.",
                "When raw loopback CDP is unavailable, Habitat degrades to cooperative CDP or snapshot mirroring and reports that mode explicitly.",
                "Component/source mapping is limited to evidence Habitat can derive from project source.",
            ],
        }

    def act(self, session_id: str, action: str, handle: str, value: str | None = None, *, screenshot: bool = False, preview: dict | None = None) -> dict:
        if value is not None and not isinstance(value, str):
            raise TypeError("UI action value must be a string or null")
        sess = self._sessions.get(session_id)
        if not sess:
            raise KeyError(session_id)
        locator = sess.page.locator(f'[data-nolane-habitat-handle="{handle}"]')
        if locator.count() != 1:
            raise ValueError(f"semantic handle must resolve to exactly one runtime element: {handle}")
        preview = preview or self.preview_action(session_id, action, handle, value)
        if action == "click": locator.click()
        elif action == "double-click": locator.dblclick()
        elif action == "hover": locator.hover()
        elif action == "focus": locator.focus()
        elif action == "fill": locator.fill(value or "")
        elif action == "select": locator.select_option(value or "")
        elif action == "check": locator.check()
        elif action == "uncheck": locator.uncheck()
        elif action == "press": locator.press(value or "Enter")
        else: raise ValueError(f"unsupported UI action: {action}")
        sess.page.wait_for_timeout(120 if sess.stream_mode == "cdp-screencast-cooperative" else 30)
        result = self.observe(session_id, screenshot=screenshot)
        result["action_receipt"] = {**preview, "value_supplied": value is not None, "url_after": result.get("url"),
                                    "frame_seq": result.get("observer_frame_seq"),
                                    "stream_seq": (result.get("observer_stream") or {}).get("seq"),
                                    "stream_epoch": (result.get("observer_stream") or {}).get("epoch"),
                                    "frame_source": result.get("observer_frame_source"),
                                    "delta_counts": {k: len((result.get("delta") or {}).get(k) or []) for k in ("added","removed","changed")},
                                    "console_count": len((result.get("events") or {}).get("console") or []),
                                    "network_count": len((result.get("events") or {}).get("network") or []),
                                    "layout_issue_count": len(result.get("layout_diagnostics") or [])}
        return result

    def assert_semantic(self, session_id: str, assertions: list[dict]) -> dict:
        """Evaluate UI assertions against semantic runtime state without screenshot/OCR interpretation."""
        if not isinstance(assertions, list) or not assertions:
            raise TypeError("assertions must be a non-empty list")
        obs = self.observe(session_id, screenshot=False)
        elements = obs.get("elements", [])
        results=[]; failures=[]
        for idx, assertion in enumerate(assertions):
            if not isinstance(assertion, dict):
                raise TypeError(f"assertions[{idx}] must be an object")
            handle=assertion.get("handle"); role=assertion.get("role"); name=assertion.get("name")
            for field_name, field_value in (("handle",handle),("role",role),("name",name)):
                if field_value is not None and not isinstance(field_value,str):
                    raise TypeError(f"assertions[{idx}].{field_name} must be a string or null")
            matches=[e for e in elements if (not handle or e.get("handle")==handle) and (not role or e.get("role")==role) and (name is None or e.get("name")==name)]
            exists=assertion.get("exists")
            if exists is not None and not isinstance(exists,bool):
                raise TypeError(f"assertions[{idx}].exists must be boolean")
            if exists is False:
                if "min_count" in assertion or "max_count" in assertion:
                    raise ValueError(f"assertions[{idx}] cannot combine exists=false with min_count/max_count")
                min_count, max_count = 0, 0
            else:
                min_raw=assertion.get("min_count",1)
                max_raw=assertion.get("max_count")
                if not isinstance(min_raw,int) or isinstance(min_raw,bool) or min_raw < 0:
                    raise ValueError(f"assertions[{idx}].min_count must be a non-negative integer")
                if max_raw is not None and (not isinstance(max_raw,int) or isinstance(max_raw,bool) or max_raw < 0):
                    raise ValueError(f"assertions[{idx}].max_count must be a non-negative integer or null")
                min_count=int(min_raw); max_count=max_raw
                if max_count is not None and int(max_count) < min_count:
                    raise ValueError(f"assertions[{idx}].max_count must be >= min_count")
            checks=[]
            count_ok=len(matches)>=min_count and (max_count is None or len(matches)<=int(max_count))
            checks.append({"field":"count","expected":{"min":min_count,"max":max_count},"actual":len(matches),"ok":count_ok})
            target=matches[0] if matches else None
            if target is not None:
                for field in ("visible","enabled","checked","value","text"):
                    if field not in assertion: continue
                    expected=assertion[field]; actual=target.get(field)
                    ok=(actual==expected)
                    checks.append({"field":field,"expected":expected,"actual":actual,"ok":ok})
                if "text_contains" in assertion:
                    expected=str(assertion["text_contains"]); actual=str(target.get("text") or "")
                    checks.append({"field":"text_contains","expected":expected,"actual":actual,"ok":expected in actual})
                if "value_contains" in assertion:
                    expected=str(assertion["value_contains"]); actual=str(target.get("value") or "")
                    checks.append({"field":"value_contains","expected":expected,"actual":actual,"ok":expected in actual})
            ok=all(c["ok"] for c in checks)
            item={"index":idx,"selector":{"handle":handle,"role":role,"name":name},"matched_handles":[e.get("handle") for e in matches[:20]],"checks":checks,"ok":ok}
            results.append(item)
            if not ok: failures.append(item)
        return {"session_id":session_id,"mode":"runtime-semantic-assertion","passed":not failures,"assertion_count":len(results),
                "failure_count":len(failures),"results":results,"failures":failures,
                "oracle":"DOM/accessibility/runtime state; pixels not consulted","screenshot_used":False}

    def close_session(self, session_id: str) -> dict:
        sess = self._sessions.pop(session_id, None)
        if not sess:
            raise KeyError(session_id)
        sess.closed = True
        self._stop_screencast(sess)
        context = sess.page.context
        try:
            context.close()
        finally:
            self._cleanup_stream_artifacts(sess)
        return {"session_id": session_id, "closed": True, "stream_closed": True, "ephemeral_frames_deleted": True}

    def close(self) -> None:
        global _SHARED_USERS
        for sid in list(self._sessions):
            with contextlib.suppress(Exception): self.close_session(sid)
        # The browser engine is shared, but every BrowserRuntime owns one lease. Closing the
        # final lease drains Playwright immediately so short-lived CLI/test processes do not
        # retain its driver thread until interpreter shutdown. Concurrent workspaces remain safe.
        with _SHARED_LOCK:
            if self._shared_acquired:
                _SHARED_USERS = max(0, _SHARED_USERS - 1)
                self._shared_acquired = False
                if _SHARED_USERS == 0:
                    _close_shared_browser()
        self._browser = None
        self._pw = None
        if self._httpd is not None:
            with contextlib.suppress(Exception): self._httpd.shutdown()
            with contextlib.suppress(Exception): self._httpd.server_close()
            if self._http_thread is not None and self._http_thread.is_alive():
                self._http_thread.join(timeout=2.0)
            self._httpd = None
            self._http_thread = None
        self._origin = None

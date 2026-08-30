from __future__ import annotations

import json
import socket
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .observability import ObservatoryReadModel
from .workspace import HabitatWorkspace
from .ui.browser_provider import frame_key_for_session

_ASSET_DIR = Path(__file__).with_name("observatory_assets")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value,ensure_ascii=False,default=str,separators=(",",":")).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    server_version="NolaneHabitatObservatory/0.1"
    def handle(self):
        try:
            return super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
            return
    def log_message(self, fmt, *args):
        return

    @property
    def obs(self):
        return self.server.observatory  # type: ignore[attr-defined]

    def _headers(self, status=200, content_type="application/json; charset=utf-8", length: int | None = None):
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Connection","close")
        self.close_connection=True
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        if length is not None: self.send_header("Content-Length",str(length))
        self.end_headers()

    def _asset(self,name,ctype):
        p=(_ASSET_DIR/name).resolve()
        if _ASSET_DIR.resolve() not in p.parents: self.send_error(404); return
        try: data=p.read_bytes()
        except FileNotFoundError: self.send_error(404); return
        self._headers(200,ctype,len(data)); self.wfile.write(data)

    def do_POST(self): self._readonly()
    def do_PUT(self): self._readonly()
    def do_PATCH(self): self._readonly()
    def do_DELETE(self): self._readonly()
    def _readonly(self):
        data=_json_bytes({"error":"observer-read-only","message":"Habitat Observatory exposes no human control actions."})
        self._headers(HTTPStatus.METHOD_NOT_ALLOWED,"application/json; charset=utf-8",len(data)); self.wfile.write(data)

    def do_GET(self):
        parsed=urllib.parse.urlsplit(self.path)
        path=parsed.path
        if path=="/": return self._asset("index.html","text/html; charset=utf-8")
        if path=="/app.js": return self._asset("app.js","application/javascript; charset=utf-8")
        if path=="/style.css": return self._asset("style.css","text/css; charset=utf-8")
        if path in {"/api/ui-frame","/api/ui-stream"}:
            q=urllib.parse.parse_qs(parsed.query); sid=(q.get("session_id") or [""])[0]
            if not sid or len(sid)>200 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:" for ch in sid): self.send_error(400); return
            live=(self.obs.workspace.habitat_dir/"artifacts"/"ui"/"live").resolve(); key=frame_key_for_session(sid); meta_path=(live/f"{key}-stream.json").resolve()
            if live not in meta_path.parents: self.send_error(404); return
            try: meta=json.loads(meta_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError): self.send_error(404); return
            if meta.get("session_id")!=sid: self.send_error(404); return
            if path=="/api/ui-stream":
                public={k:meta.get(k) for k in ("session_id","status","frame_seq","stream_seq","stream_epoch","stream_mode","stream_active","frame_at","frame_source","poll_hint_ms")}
                data=_json_bytes(public); self._headers(200,"application/json; charset=utf-8",len(data)); self.wfile.write(data); return
            raw_seq=(q.get("seq") or [None])[0]
            try: seq=int(raw_seq) if raw_seq is not None else int(meta.get("frame_seq") or 0)
            except Exception: self.send_error(400); return
            if seq<=0: self.send_error(404); return
            frame=(live/f"{key}-frame-{seq:09d}.png").resolve()
            if live not in frame.parents: self.send_error(404); return
            try: data=frame.read_bytes()
            except (FileNotFoundError, OSError): self.send_error(404); return
            self._headers(200,"image/png",len(data)); self.wfile.write(data); return
        if path=="/api/snapshot":
            data=_json_bytes(self.obs.read_model.snapshot())
            self._headers(200,"application/json; charset=utf-8",len(data)); self.wfile.write(data); return
        if path=="/api/activity":
            q=urllib.parse.parse_qs(parsed.query)
            try: since=max(0,int((q.get("since") or ["0"])[0]))
            except Exception: since=0
            data=_json_bytes(self.obs.read_model.activity_since(since,500))
            self._headers(200,"application/json; charset=utf-8",len(data)); self.wfile.write(data); return
        if path=="/api/health":
            data=_json_bytes({"ok":True,"read_only":True,"revision":self.obs.read_model.revision(),"url":self.obs.url})
            self._headers(200,"application/json; charset=utf-8",len(data)); self.wfile.write(data); return
        if path=="/events": return self._sse()
        self.send_error(404)

    def _sse(self):
        self.close_connection=True
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        raw_since=(q.get("since") or [None])[0]
        if raw_since is None: raw_since=self.headers.get("Last-Event-ID") or "0"
        try: seq=max(0,int(raw_since))
        except Exception: seq=0
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream; charset=utf-8")
        self.send_header("Cache-Control","no-cache")
        self.send_header("Connection","keep-alive")
        self.send_header("X-Accel-Buffering","no")
        self.end_headers()
        try:
            initial=self.obs.read_model.activity_since(seq,1)
            hello={"type":"observatory.connected","revision":self.obs.read_model.revision(),"read_only":True,"seq":seq,"oldest_seq":initial.get("oldest_seq",0),"latest_seq":initial.get("latest_seq",0),"resumable":True}
            self.wfile.write(b"retry: 1200\nevent: hello\ndata: "+_json_bytes(hello)+b"\n\n")
            if initial.get("gap_detected"):
                gap={"type":"observatory.activity-gap","requested_seq":seq,"oldest_seq":initial.get("oldest_seq"),"latest_seq":initial.get("latest_seq")}
                self.wfile.write(b"event: gap\ndata: "+_json_bytes(gap)+b"\n\n"); seq=max(0,int(initial.get("oldest_seq") or 1)-1)
            self.wfile.flush(); heartbeat=time.monotonic()
            while not self.obs.closed.is_set():
                batch=self.obs.read_model.activity_since(seq,200)
                if batch.get("gap_detected"):
                    gap={"type":"observatory.activity-gap","requested_seq":seq,"oldest_seq":batch.get("oldest_seq"),"latest_seq":batch.get("latest_seq")}
                    self.wfile.write(b"event: gap\ndata: "+_json_bytes(gap)+b"\n\n"); seq=max(0,int(batch.get("oldest_seq") or 1)-1)
                    batch=self.obs.read_model.activity_since(seq,200)
                for event in batch.get("events",[]):
                    seq=max(seq,int(event.get("seq") or 0))
                    self.wfile.write(b"id: "+str(seq).encode()+b"\nevent: activity\ndata: "+_json_bytes(event)+b"\n\n")
                if batch.get("events"):
                    self.wfile.flush(); heartbeat=time.monotonic()
                elif time.monotonic()-heartbeat>=10:
                    self.wfile.write(b": heartbeat\n\n"); self.wfile.flush(); heartbeat=time.monotonic()
                self.obs.closed.wait(0.35)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,OSError):
            return


class _ThreadingHTTPServerV6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


class ObservatoryServer:
    """Read-only real-time visual observatory for a live Habitat workspace."""
    def __init__(self, workspace: HabitatWorkspace, host: str="127.0.0.1", port: int=0):
        if host not in {"127.0.0.1","localhost","::1"}:
            raise ValueError("Observatory binds loopback only; remote exposure requires an explicit external reverse proxy/security layer")
        self.workspace=workspace; self.read_model=ObservatoryReadModel(workspace); self.host=host; self.port=int(port); self.closed=threading.Event(); self.thread=None
        server_cls=_ThreadingHTTPServerV6 if host=="::1" else ThreadingHTTPServer
        self.httpd=server_cls((host,self.port),_Handler)
        self.httpd.daemon_threads=True
        self.httpd.observatory=self  # type: ignore[attr-defined]
        addr=self.httpd.server_address
        raw_host="127.0.0.1" if addr[0] in {"0.0.0.0","::"} else addr[0]
        display_host=f"[{raw_host}]" if ":" in raw_host and not raw_host.startswith("[") else raw_host
        self.url=f"http://{display_host}:{addr[1]}/"
    def start(self, *, open_browser: bool=False):
        if self.thread and self.thread.is_alive(): return self
        self.thread=threading.Thread(target=self.httpd.serve_forever,name="habitat-observatory",daemon=True); self.thread.start()
        if open_browser:
            try: webbrowser.open(self.url,new=2,autoraise=True)
            except Exception: pass
        return self
    def close(self):
        if self.closed.is_set(): return
        self.closed.set()
        try: self.httpd.shutdown()
        except Exception: pass
        try: self.httpd.server_close()
        except Exception: pass
        if self.thread and self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=2)
    def status(self):
        return {"running":bool(self.thread and self.thread.is_alive() and not self.closed.is_set()),"url":self.url,"read_only":True,"host":self.host,"port":self.httpd.server_address[1]}

from __future__ import annotations
import json
import math
import time
from dataclasses import dataclass
from typing import Any
from .model import to_dict
from .operation_registry import OPERATION_REGISTRY
from .workspace import HabitatWorkspace

PROTOCOL_VERSION = "habitat.agent.v1alpha2"
MAX_REQUEST_BYTES = 256 * 1024

@dataclass
class ProtocolError(Exception):
    code: str; message: str; details: dict[str, Any] | None = None
    def __str__(self): return self.message


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _reject_nonstandard_number(_value: str) -> None:
    raise ValueError("non-standard number")


def _parse_finite_float(value: str) -> float:
    parsed=float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite number")
    return parsed


def _contains_unpaired_surrogate(value: Any) -> bool:
    if isinstance(value, str):
        return any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    if isinstance(value, dict):
        return any(_contains_unpaired_surrogate(key) or _contains_unpaired_surrogate(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_unpaired_surrogate(item) for item in value)
    return False


def parse_json_request(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8", errors="surrogatepass")) > MAX_REQUEST_BYTES:
        raise ProtocolError("REQUEST_TOO_LARGE", "request exceeds the protocol size limit")
    try:
        request = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
            parse_float=_parse_finite_float,
        )
    except (json.JSONDecodeError, ValueError):
        raise ProtocolError("INVALID_JSON", "request must be strict JSON") from None
    if not isinstance(request, dict):
        raise ProtocolError("INVALID_REQUEST", "request must be a JSON object")
    if _contains_unpaired_surrogate(request):
        raise ProtocolError("INVALID_REQUEST", "request contains an unpaired surrogate")
    return request

class HabitatProtocol:
    # These operations are safe projections. They must not create activity or trace rows merely
    # because a client observed state; additions require logical-state conformance evidence.
    READ_ONLY_METHODS = OPERATION_REGISTRY.read_only_names
    METHODS = list(OPERATION_REGISTRY.names)

    def __init__(self, workspace: HabitatWorkspace): self.workspace=workspace
    @staticmethod
    def _exact_source_bytes(value: Any) -> int:
        total = 0
        if isinstance(value, dict):
            source = value.get("source")
            authority = str(value.get("source_authority") or value.get("authority") or "").lower()
            if isinstance(source, str) and ("exact" in authority or authority == "exact-source"):
                total += len(source.encode("utf-8"))
            for k, v in value.items():
                if k == "source":
                    continue
                total += HabitatProtocol._exact_source_bytes(v)
        elif isinstance(value, list):
            total += sum(HabitatProtocol._exact_source_bytes(v) for v in value)
        return total

    def handle(self, request: Any) -> dict[str, Any]:
        started = time.perf_counter()
        if not isinstance(request, dict):
            return self._error(None, "INVALID_REQUEST", "request must be a JSON object")
        if _contains_unpaired_surrogate(request):
            return self._error(request.get("id"), "INVALID_REQUEST", "request contains an unpaired surrogate")
        rid=request.get("id"); method=request.get("method"); params=request.get("params") or {}
        if not isinstance(method,str):
            response=self._error(rid,"INVALID_REQUEST","method must be a string")
        elif not isinstance(params,dict):
            response=self._error(rid,"INVALID_REQUEST","params must be an object")
        else:
            activity_allowed=(
                method not in self.READ_ONLY_METHODS
                and not method.startswith(("workspace.activity.","workspace.observatory.","workspace.trace."))
            )
            agent_id=params.get("agent_id") if isinstance(params.get("agent_id"),str) else None
            episode_id=params.get("episode_id") if isinstance(params.get("episode_id"),str) else None
            path=params.get("path") if isinstance(params.get("path"),str) else None
            if activity_allowed:
                try: self.workspace.activity_emit("tool.started","tool",agent_id=agent_id,episode_id=episode_id,ref_id=method,path=path,status="running",summary=method,data={"request_id":rid})
                except Exception: pass
            try:
                result=self._dispatch(method,params)
                response={"protocol":PROTOCOL_VERSION,"id":rid,"ok":True,"revision":self.workspace.revision,"result":to_dict(result)}
            except KeyError as exc: response=self._error(rid,"NOT_FOUND",str(exc))
            except (ValueError,TypeError) as exc: response=self._error(rid,"INVALID_PARAMS",str(exc))
            except Exception as exc: response=self._error(rid,type(exc).__name__.upper(),str(exc))
            if activity_allowed:
                try:
                    r=response.get("result") if isinstance(response,dict) else None
                    changed=(r.get("changed_paths") if isinstance(r,dict) else None) or ((r.get("transaction") or {}).get("changed_paths") if isinstance(r,dict) and isinstance(r.get("transaction"),dict) else None) or []
                    self.workspace.activity_emit("tool.completed","tool",agent_id=agent_id,episode_id=episode_id,ref_id=method,path=(changed[0] if changed else path),status="passed" if response.get("ok") else "failed",summary=method+(" completed" if response.get("ok") else " failed"),data={"request_id":rid,"changed_paths":changed[:20],"error":response.get("error") if not response.get("ok") else None})
                except Exception: pass
        # Trace is measurement infrastructure, not a source-state mutation. Control calls are excluded so
        # start/stop do not bias the measured workload they bracket.
        if isinstance(method,str) and method not in self.READ_ONLY_METHODS and not method.startswith("workspace.trace."):
            try:
                req_bytes=len(json.dumps(request,ensure_ascii=False,default=str,separators=(",",":")).encode("utf-8"))
                resp_bytes=len(json.dumps(response,ensure_ascii=False,default=str,separators=(",",":")).encode("utf-8"))
                source_bytes=self._exact_source_bytes(response)
                self.workspace.record_trace_call(method,bool(response.get("ok")),int((time.perf_counter()-started)*1000),req_bytes,resp_bytes,source_bytes)
            except Exception:
                # Telemetry must never change the agent operation result.
                pass
        return response
    @staticmethod
    def _int(p,k,default=None):
        if k not in p:
            if default is None: raise ValueError(f"missing required parameter: {k}")
            return default
        v=p[k]
        if not isinstance(v,int) or isinstance(v,bool): raise TypeError(f"{k} must be int")
        return v
    @staticmethod
    def _bool(p,k,default=None):
        if k not in p:
            if default is None: raise ValueError(f"missing required parameter: {k}")
            return default
        v=p[k]
        if not isinstance(v,bool): raise TypeError(f"{k} must be bool")
        return v
    @staticmethod
    def _float(p,k,default=None):
        if k not in p:
            if default is None: raise ValueError(f"missing required parameter: {k}")
            return default
        v=p[k]
        if not isinstance(v,(int,float)) or isinstance(v,bool): raise TypeError(f"{k} must be number")
        return float(v)

    @staticmethod
    def _optional(p,k,t):
        if k not in p or p[k] is None: return None
        if not isinstance(p[k],t): raise TypeError(f"{k} must be {t.__name__}")
        return p[k]

    def _dispatch(self,m,p):
        descriptor = OPERATION_REGISTRY.get(m)
        if descriptor is None:
            raise KeyError(f"unknown method: {m}")
        return descriptor.handler(self, p)

    @staticmethod
    def _required(p,k,t):
        if k not in p: raise ValueError(f"missing required parameter: {k}")
        v=p[k]
        if not isinstance(v,t): raise TypeError(f"{k} must be {t.__name__}")
        return v
    def _error(self,rid,code,message,details=None):
        return {"protocol":PROTOCOL_VERSION,"id":rid,"ok":False,"revision":self.workspace.revision,"error":{"code":code,"message":message,"details":details or {}}}

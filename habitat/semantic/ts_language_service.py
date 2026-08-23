from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from .typescript import _probe
from ..util import stable_id


TS_SERVICE_RESPONSE_TIMEOUT_S = 30.0


TS_SERVICE_SCRIPT = r'''
const fs=require('fs'); const path=require('path'); const readline=require('readline');
let ts; try{ts=require('typescript')}catch(e){ if(process.env.NOLANE_TYPESCRIPT_PATH) ts=require(process.env.NOLANE_TYPESCRIPT_PATH); else throw e; }
let state={root:null,files:[],versions:new Map(),texts:new Map(),service:null,options:null,requestCount:0,sessionId:'tsls-'+process.pid};
function rel(root,f){return path.relative(root,f).split(path.sep).join('/');}
function reset(root, files){
  state.root=path.resolve(root); state.files=files.slice(); state.versions=new Map(); state.texts=new Map(); state.requestCount=0;
  let options={allowJs:true,checkJs:false,noEmit:true,skipLibCheck:true,target:ts.ScriptTarget.ES2022,moduleResolution:ts.ModuleResolutionKind.NodeJs,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.Preserve};
  const configPath=ts.findConfigFile(state.root,ts.sys.fileExists,'tsconfig.json')||ts.findConfigFile(state.root,ts.sys.fileExists,'jsconfig.json');
  if(configPath){try{const cfg=ts.readConfigFile(configPath,ts.sys.readFile);const parsed=ts.parseJsonConfigFileContent(cfg.config,ts.sys,path.dirname(configPath));options={...options,...parsed.options,noEmit:true};}catch(e){}}
  state.options=options;
  const host={
    getScriptFileNames:()=>state.files.map(f=>path.resolve(state.root,f)),
    getScriptVersion:(f)=>state.versions.get(path.normalize(f))||'0',
    getScriptSnapshot:(f)=>{
      const k=path.normalize(f); let text=state.texts.get(k);
      if(text===undefined){try{text=fs.readFileSync(f,'utf8');state.texts.set(k,text);}catch(e){return undefined;}}
      return ts.ScriptSnapshot.fromString(text);
    },
    getCurrentDirectory:()=>state.root,
    getCompilationSettings:()=>state.options,
    getDefaultLibFileName:(o)=>ts.getDefaultLibFilePath(o),
    fileExists:ts.sys.fileExists, readFile:ts.sys.readFile, readDirectory:ts.sys.readDirectory,
    directoryExists:ts.sys.directoryExists, getDirectories:ts.sys.getDirectories,
  };
  state.service=ts.createLanguageService(host,ts.createDocumentRegistry());
}
function position(sf,node){const lc=sf.getLineAndCharacterOfPosition(node.getStart(sf));return {line:lc.line+1,column:lc.character+1};}
function declaredName(node){if(node&&node.name&&node.name.getText)return node.name.getText();if(node&&ts.isVariableDeclaration(node)&&node.name)return node.name.getText();return null;}
function container(node){let cur=node.parent;while(cur){if(ts.isFunctionDeclaration(cur)||ts.isMethodDeclaration(cur)||ts.isClassDeclaration(cur)||ts.isArrowFunction(cur)||ts.isFunctionExpression(cur)){if((ts.isArrowFunction(cur)||ts.isFunctionExpression(cur))&&cur.parent&&ts.isVariableDeclaration(cur.parent))cur=cur.parent;const n=declaredName(cur);if(n)return {name:n,...position(cur.getSourceFile(),cur)};}cur=cur.parent;}return null;}
function analyze(input){
  const root=path.resolve(input.root); const files=(input.files||[]).slice().sort(); const previousFiles=state.files.join('\0');
  let resetNeeded=!state.service||state.root!==root;
  if(resetNeeded) reset(root,files); else state.files=files;
  let hydrated=0; let removed=0;
  const wanted=new Set(files.map(f=>path.normalize(path.resolve(root,f))));
  for(const k of Array.from(state.versions.keys())){if(!wanted.has(k)){state.versions.delete(k);state.texts.delete(k);removed++;}}
  for(const x of (input.file_states||[])){
    const abs=path.normalize(path.resolve(root,x.path)); const ver=String(x.version||x.digest||'0');
    if(state.versions.get(abs)!==ver){let text=fs.readFileSync(abs,'utf8');state.versions.set(abs,ver);state.texts.set(abs,text);hydrated++;}
  }
  state.requestCount++;
  const program=state.service.getProgram(); if(!program) throw new Error('TypeScript language service produced no program');
  const checker=program.getTypeChecker(); const allowed=new Set(files.map(f=>path.normalize(path.resolve(root,f))));
  const scan=new Set((input.scan_files||files).map(f=>path.normalize(path.resolve(root,f))));
  const out={calls:[],imports:[],provider_version:ts.version,session_id:state.sessionId,request_count:state.requestCount,session_reused:state.requestCount>1&&!resetNeeded,hydrated_files:hydrated,removed_files:removed,file_set_changed:previousFiles!==files.join('\0')};
  function targetFromSymbol(sym){if(!sym)return null;try{if(sym.flags&ts.SymbolFlags.Alias)sym=checker.getAliasedSymbol(sym);}catch(e){}const decl=(sym.valueDeclaration||(sym.declarations&&sym.declarations[0]));if(!decl)return null;const sf=decl.getSourceFile();if(!sf||!allowed.has(path.normalize(sf.fileName)))return null;const p=position(sf,decl);return {path:rel(root,sf.fileName),name:(sym.getName&&sym.getName())||declaredName(decl),line:p.line,column:p.column};}
  for(const sf of program.getSourceFiles()){
    const n=path.normalize(sf.fileName); if(!allowed.has(n)||!scan.has(n))continue;
    function visit(node){
      if(ts.isImportDeclaration(node)&&node.moduleSpecifier&&ts.isStringLiteral(node.moduleSpecifier)){
        const spec=node.moduleSpecifier.text; const resolved=ts.resolveModuleName(spec,sf.fileName,state.options,ts.sys).resolvedModule;
        if(resolved&&allowed.has(path.normalize(resolved.resolvedFileName))){const p=position(sf,node);out.imports.push({source_path:rel(root,sf.fileName),target_path:rel(root,resolved.resolvedFileName),line:p.line,column:p.column,spec});}
      }
      if(ts.isCallExpression(node)){let lookup=node.expression;if(ts.isPropertyAccessExpression(node.expression))lookup=node.expression.name;const target=targetFromSymbol(checker.getSymbolAtLocation(lookup));if(target){const p=position(sf,node);out.calls.push({source_path:rel(root,sf.fileName),source_container:container(node),target,line:p.line,column:p.column,text:node.expression.getText(sf).slice(0,300)});}}
      ts.forEachChild(node,visit);
    } visit(sf);
  }
  return out;
}
const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
rl.on('line',(line)=>{if(!line.trim())return;let req;try{req=JSON.parse(line);if(req.cmd==='close'){process.stdout.write(JSON.stringify({ok:true,closed:true})+'\n');process.exit(0);}const result=analyze(req);process.stdout.write(JSON.stringify({ok:true,result})+'\n');}catch(e){process.stdout.write(JSON.stringify({ok:false,error:String(e&&e.stack||e)})+'\n');}});
'''


class TypeScriptLanguageServiceProcess:
    def __init__(self, root: Path):
        ok, reason, module_path = _probe()
        if not ok:
            raise RuntimeError(reason)
        env=os.environ.copy()
        if module_path:
            env.setdefault("NOLANE_TYPESCRIPT_PATH",module_path)
        self.root=root.resolve(); self._lock=threading.Lock(); self._closed=False
        self.proc=subprocess.Popen(
            [shutil.which("node") or "node","-e",TS_SERVICE_SCRIPT],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,env=env,
        )
        self.local_session_id=stable_id("ts-language-service",str(self.root),str(self.proc.pid))
        self.last_result: dict[str, Any] = {}

    def analyze(self, files: list[str], file_states: list[dict[str, Any]], scan_files: list[str]) -> dict:
        if self._closed or self.proc.poll() is not None:
            raise RuntimeError("TypeScript language service is not running")
        req={"cmd":"analyze","root":str(self.root),"files":files,"file_states":file_states,"scan_files":scan_files}
        with self._lock:
            if self._closed or self.proc.poll() is not None:
                raise RuntimeError("TypeScript language service is not running")
            assert self.proc.stdin is not None and self.proc.stdout is not None
            self.proc.stdin.write(json.dumps(req,separators=(",",":"))+"\n"); self.proc.stdin.flush()
            responses: queue.Queue[str | Exception] = queue.Queue(maxsize=1)

            def read_response() -> None:
                try:
                    responses.put(self.proc.stdout.readline())
                except Exception as exc:
                    responses.put(exc)

            threading.Thread(target=read_response, daemon=True).start()
            try:
                line=responses.get(timeout=TS_SERVICE_RESPONSE_TIMEOUT_S)
            except queue.Empty:
                self.close()
                raise RuntimeError(f"TypeScript language service timed out after {TS_SERVICE_RESPONSE_TIMEOUT_S:g}s")
            if isinstance(line, Exception):
                raise line
        if not line:
            err=""
            if self.proc.stderr is not None:
                try: err=self.proc.stderr.read(2000)
                except Exception: pass
            raise RuntimeError(f"TypeScript language service exited without response: {err}")
        value=json.loads(line)
        if not value.get("ok"):
            raise RuntimeError(str(value.get("error") or "TypeScript language service failed"))
        self.last_result=dict(value["result"])
        return dict(self.last_result)

    def close(self) -> None:
        if self._closed: return
        self._closed=True
        try:
            if self.proc.poll() is None and self.proc.stdin is not None:
                self.proc.stdin.write('{"cmd":"close"}\n'); self.proc.stdin.flush()
                self.proc.wait(timeout=1.5)
        except Exception:
            try: self.proc.kill(); self.proc.wait(timeout=1.0)
            except Exception: pass
        finally:
            for stream in (self.proc.stdin,self.proc.stdout,self.proc.stderr):
                try:
                    if stream is not None: stream.close()
                except Exception:
                    pass


_sessions: dict[str, TypeScriptLanguageServiceProcess] = {}
_sessions_lock=threading.Lock()
_MAX_SESSIONS=4


def get_typescript_session(root: Path) -> TypeScriptLanguageServiceProcess:
    key=str(root.resolve())
    with _sessions_lock:
        session=_sessions.get(key)
        if session is not None and session.proc.poll() is None:
            return session
        if session is not None:
            session.close(); _sessions.pop(key,None)
        if len(_sessions) >= _MAX_SESSIONS:
            old_key=next(iter(_sessions)); _sessions.pop(old_key).close()
        session=TypeScriptLanguageServiceProcess(root); _sessions[key]=session; return session


def typescript_session_status(root: Path) -> dict:
    key=str(root.resolve())
    with _sessions_lock:
        session=_sessions.get(key)
        if session is None:
            return {"running":False,"root":key}
        return {"running":session.proc.poll() is None,"root":key,"pid":session.proc.pid,
                "local_session_id":session.local_session_id,"last_result":dict(session.last_result)}

def close_typescript_session(root: Path) -> None:
    key=str(root.resolve())
    with _sessions_lock:
        session=_sessions.pop(key,None)
    if session is not None: session.close()


def close_all_typescript_sessions() -> None:
    with _sessions_lock:
        items=list(_sessions.values()); _sessions.clear()
    for item in items: item.close()


atexit.register(close_all_typescript_sessions)

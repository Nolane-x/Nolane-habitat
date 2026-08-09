from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from .base import SemanticParseResult, SemanticProvider
from ..model import DiagnosticRecord, SymbolRecord
from ..util import stable_id

NODE_SCRIPT = r'''
const fs = require('fs');
let ts;
try { ts = require('typescript'); }
catch (e) {
  if (process.env.NOLANE_TYPESCRIPT_PATH) ts = require(process.env.NOLANE_TYPESCRIPT_PATH);
  else throw e;
}
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const kind = input.path.endsWith('.tsx') ? ts.ScriptKind.TSX :
             input.path.endsWith('.jsx') ? ts.ScriptKind.JSX :
             input.path.endsWith('.js') ? ts.ScriptKind.JS : ts.ScriptKind.TS;
const sf = ts.createSourceFile(input.path, input.text, ts.ScriptTarget.Latest, true, kind);
const out = {symbols: [], relations: [], diagnostics: [], ui_elements: []};
function posLine(pos){ return sf.getLineAndCharacterOfPosition(pos).line + 1; }
function nodeName(node){ return node.name && node.name.getText(sf) || null; }
function ownerName(node){
  let cur=node.parent;
  while(cur){
    if ((ts.isFunctionDeclaration(cur)||ts.isMethodDeclaration(cur)||ts.isClassDeclaration(cur)) && cur.name) return cur.name.getText(sf);
    if ((ts.isArrowFunction(cur)||ts.isFunctionExpression(cur)) && cur.parent && ts.isVariableDeclaration(cur.parent) && ts.isIdentifier(cur.parent.name)) return cur.parent.name.text;
    cur=cur.parent;
  }
  return null;
}
function add(node, name, skind, qname){
  if (!name) return;
  out.symbols.push({
    name, qualified_name: qname || name, kind: skind,
    start_line: posLine(node.getStart(sf)), end_line: posLine(node.getEnd()),
    signature: node.getText(sf).split(/\r?\n/)[0].slice(0, 500)
  });
}
const stack=[];
function visit(node){
  let pushed=false;
  if (ts.isClassDeclaration(node) && node.name) { const n=node.name.text; add(node,n,'class',[...stack,n].join('.')); stack.push(n); pushed=true; }
  else if (ts.isInterfaceDeclaration(node)) { const n=node.name.text; add(node,n,'interface',[...stack,n].join('.')); stack.push(n); pushed=true; }
  else if (ts.isEnumDeclaration(node)) { const n=node.name.text; add(node,n,'enum',[...stack,n].join('.')); }
  else if (ts.isTypeAliasDeclaration(node)) { const n=node.name.text; add(node,n,'type',[...stack,n].join('.')); }
  else if (ts.isFunctionDeclaration(node) && node.name) { const n=node.name.text; add(node,n,'function',[...stack,n].join('.')); stack.push(n); pushed=true; }
  else if (ts.isMethodDeclaration(node) && node.name) { const n=node.name.getText(sf); add(node,n,'method',[...stack,n].join('.')); stack.push(n); pushed=true; }
  else if (ts.isVariableStatement(node)) {
    for (const d of node.declarationList.declarations) {
      if (ts.isIdentifier(d.name) && d.initializer && (ts.isArrowFunction(d.initializer) || ts.isFunctionExpression(d.initializer))) {
        const n=d.name.text; add(d,n,'function',[...stack,n].join('.'));
      }
    }
  }
  if (ts.isImportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
    out.relations.push({target: node.moduleSpecifier.text, kind:'imports_module', trust:'parser', evidence:'line '+posLine(node.getStart(sf))});
  }
  if (ts.isCallExpression(node)) {
    let n=null;
    if (ts.isIdentifier(node.expression)) n=node.expression.text;
    else if (ts.isPropertyAccessExpression(node.expression)) n=node.expression.name.text;
    if (n && stack.length) out.relations.push({source_name: stack.join('.'), target:n, kind:'calls_name', trust:'parser', evidence:'line '+posLine(node.getStart(sf))});
  }
  if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
    const attrs=node.attributes && node.attributes.properties || [];
    const anchors=[]; const handlers=[];
    for (const a of attrs) {
      if (!ts.isJsxAttribute(a) || !a.name) continue;
      const an=a.name.getText(sf);
      if (an==='id' || an==='data-testid') {
        let val=null;
        if (a.initializer && ts.isStringLiteral(a.initializer)) val=a.initializer.text;
        if (val) anchors.push({attribute:an,key:val});
      }
      if (/^on[A-Z]/.test(an) && a.initializer && ts.isJsxExpression(a.initializer) && a.initializer.expression) {
        const expr=a.initializer.expression; let handlerName=null;
        if (ts.isIdentifier(expr)) handlerName=expr.text;
        else if (ts.isPropertyAccessExpression(expr)) handlerName=expr.name.text;
        if (handlerName) handlers.push({event:an.slice(2).toLowerCase(),name:handlerName,text:expr.getText(sf).slice(0,300)});
      }
    }
    for (const a of anchors) out.ui_elements.push({key:a.key, attribute:a.attribute, tag:node.tagName.getText(sf), line:posLine(node.getStart(sf)), owner:ownerName(node), handlers});
  }
  ts.forEachChild(node, visit);
  if (pushed) stack.pop();
}
visit(sf);
for (const d of sf.parseDiagnostics || []) {
  const lc = d.start == null ? {line:0, character:0} : sf.getLineAndCharacterOfPosition(d.start);
  out.diagnostics.push({severity:'error', message:ts.flattenDiagnosticMessageText(d.messageText,' '), line:lc.line+1, column:lc.character+1});
}
process.stdout.write(JSON.stringify(out));
'''


@lru_cache(maxsize=1)
def _probe() -> tuple[bool, str, str | None]:
    node = shutil.which("node")
    if not node:
        return False, "node executable not found", None
    try:
        proc = subprocess.run(
            [node, "-e", "console.log(require.resolve('typescript'))"],
            text=True, capture_output=True, timeout=5, check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return True, "TypeScript compiler API resolved by Node", proc.stdout.strip()
    except Exception:
        pass
    return False, "TypeScript compiler module not resolvable by Node", None




@lru_cache(maxsize=1)
def provider_version() -> str | None:
    ok, _, module_path = _probe()
    if not ok:
        return None
    env = None
    if module_path:
        import os
        env = os.environ.copy()
        env.setdefault("NOLANE_TYPESCRIPT_PATH", module_path)
    try:
        proc = subprocess.run(
            [shutil.which("node") or "node", "-e", "let ts; try{ts=require('typescript')}catch(e){ts=require(process.env.NOLANE_TYPESCRIPT_PATH)}; process.stdout.write(String(ts.version||''))"],
            text=True, capture_output=True, timeout=5, check=False, env=env,
        )
        return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None
    except Exception:
        return None


class TypeScriptCompilerProvider(SemanticProvider):
    id = "typescript-compiler-api"
    languages = frozenset({"javascript", "typescript"})

    def available(self) -> tuple[bool, str]:
        ok, reason, _ = _probe()
        return ok, reason

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        ok, reason, module_path = _probe()
        rel = path.relative_to(root).as_posix()
        if not ok:
            return SemanticParseResult(self.id, False, reason=reason)
        env = None
        if module_path:
            # Normal require() already works on the probed host. Keep the path available for runtimes
            # that need an explicit override without changing project dependencies.
            import os
            env = os.environ.copy()
            env.setdefault("NOLANE_TYPESCRIPT_PATH", module_path)
        try:
            proc = subprocess.run(
                [shutil.which("node") or "node", "-e", NODE_SCRIPT],
                input=json.dumps({"path": rel, "text": text}), text=True,
                capture_output=True, timeout=10, check=False, env=env,
            )
        except Exception as exc:
            return SemanticParseResult(self.id, False, reason=f"provider execution failed: {exc}")
        if proc.returncode != 0:
            return SemanticParseResult(self.id, False, reason=(proc.stderr or "provider failed")[:1000])
        try:
            value = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return SemanticParseResult(self.id, False, reason=f"invalid provider output: {exc}")

        symbols: list[SymbolRecord] = []
        qname_to_id: dict[str, str] = {}
        for item in value.get("symbols", []):
            qname = item.get("qualified_name") or item["name"]
            sid = stable_id("sym", rel, item["kind"], qname)
            qname_to_id[qname] = sid
            symbols.append(SymbolRecord(
                sid, file_id, rel, item["name"], qname, item["kind"],
                "typescript" if path.suffix.lower() in {".ts", ".tsx"} else "javascript",
                int(item.get("start_line") or 1), int(item.get("end_line") or item.get("start_line") or 1),
                item.get("signature"), None, "parser",
            ))
        ui_items = value.get("ui_elements", [])
        ui_owner = {}
        ui_handlers = {}
        seen_ui = set()
        for item in ui_items:
            key = str(item.get("key") or "")
            line = int(item.get("line") or 1)
            if not key or (key, line) in seen_ui:
                continue
            seen_ui.add((key, line))
            sid = stable_id("ui", rel, "jsx-element", key, str(line))
            symbols.append(SymbolRecord(
                sid, file_id, rel, key, key, "ui-element",
                "typescript" if path.suffix.lower() in {".ts", ".tsx"} else "javascript",
                line, line, f"{item.get('tag') or 'jsx'} [{item.get('attribute') or 'anchor'}={key}]",
                f"JSX anchor owned by {item.get('owner')}" if item.get("owner") else "JSX anchor", "parser",
            ))
            ui_owner[sid] = item.get("owner")
            ui_handlers[sid] = list(item.get("handlers") or [])
        unresolved = []
        for sym in symbols:
            if "." in sym.qualified_name:
                parent_q = sym.qualified_name.rsplit(".", 1)[0]
                parent_id = qname_to_id.get(parent_q)
                if parent_id:
                    unresolved.append((parent_id, sym.id, "contains", "parser", "TypeScript AST nesting"))
        for sym in symbols:
            if sym.kind == "ui-element" and sym.id in ui_owner:
                owner = ui_owner.get(sym.id)
                source = next((x.id for x in symbols if owner and (x.name == owner or x.qualified_name.split(".")[-1] == owner) and x.kind in {"function","method","class"}), file_id)
                unresolved.append((source, sym.id, "renders", "parser", f"JSX anchor line {sym.start_line}"))
                for handler in ui_handlers.get(sym.id, []):
                    hname = str(handler.get("name") or "").strip()
                    event = str(handler.get("event") or "event").strip().lower()
                    if hname:
                        unresolved.append((sym.id, hname, "ui_handler_name", "parser", f"JSX on{event} handler line {sym.start_line}"))
        for r in value.get("relations", []):
            source = file_id
            if r.get("source_name"):
                source = qname_to_id.get(r["source_name"], source)
            unresolved.append((source, r.get("target") or "", r.get("kind") or "related", r.get("trust") or "parser", r.get("evidence")))
        diagnostics = []
        for d in value.get("diagnostics", []):
            msg = str(d.get("message") or "TypeScript parse diagnostic")
            line = int(d.get("line") or 0) or None
            col = int(d.get("column") or 0) or None
            diagnostics.append(DiagnosticRecord(
                stable_id("diag", rel, str(line), str(col), msg), file_id, rel,
                str(d.get("severity") or "error"), msg, line, col, self.id, "parser"
            ))
        return SemanticParseResult(self.id, True, symbols, unresolved, diagnostics, reason)

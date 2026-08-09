from __future__ import annotations
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

@dataclass
class UIElement:
    id: str; tag: str; role: str; name: str | None; attributes: dict[str,str]; text: str=""

class SemanticHTMLParser(HTMLParser):
    def __init__(self,path):
        super().__init__(convert_charrefs=True); self.path=path; self.elements=[]; self.stack=[]; self.counter=0; self.labels={}; self.label_stack=[]
    @staticmethod
    def _role(tag,attrs):
        if "role" in attrs:return attrs["role"]
        if tag=="input":
            t=attrs.get("type","text").lower(); return "checkbox" if t=="checkbox" else "radio" if t=="radio" else "button" if t in {"submit","button"} else "textbox"
        return {"button":"button","a":"link","textarea":"textbox","select":"combobox","form":"form","nav":"navigation","main":"main","h1":"heading","h2":"heading","h3":"heading","img":"img"}.get(tag,"generic")
    def handle_starttag(self,tag,attrs_list):
        attrs={k:(v or "") for k,v in attrs_list}
        if tag in {"script","style","meta","link"}: return
        self.counter+=1; identity=attrs.get("id") or attrs.get("name") or f"{tag}-{self.counter}"
        name=attrs.get("aria-label") or attrs.get("placeholder") or attrs.get("alt") or attrs.get("title")
        el=UIElement(f"ui:{self.path}#{identity}",tag,self._role(tag,attrs),name,attrs); self.elements.append(el)
        if tag=="label": self.label_stack.append((attrs.get("for"),el))
        if tag not in {"input","img","br","hr","source","area","base","embed","param","track","wbr"}: self.stack.append(el)
    def handle_endtag(self,tag):
        if tag=="label" and self.label_stack:
            target,el=self.label_stack.pop()
            if target and el.text:self.labels[target]=el.text
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i].tag==tag: del self.stack[i:]; break
    def handle_data(self,data):
        text=" ".join(data.split())
        if not text or not self.stack:return
        el=self.stack[-1]; el.text=(el.text+" "+text).strip()[:500]
        if not el.name and el.tag in {"button","a","h1","h2","h3","label","option"}: el.name=el.text
    def finalize(self):
        for el in self.elements:
            if not el.name and el.attributes.get("id") in self.labels: el.name=self.labels[el.attributes["id"]]

def observe_html(root: Path, relpath: str) -> dict[str,Any]:
    path=(root/relpath).resolve()
    if root.resolve() not in path.parents and path!=root.resolve(): raise ValueError("path escapes workspace")
    parser=SemanticHTMLParser(relpath); parser.feed(path.read_text(encoding="utf-8",errors="replace")); parser.finalize()
    return {"surface":f"file:{relpath}","mode":"semantic-static-html","limitations":["Static observer does not execute JavaScript.","Use ui.runtime.* for runtime DOM/ARIA/layout/action state."],"elements":[asdict(e) for e in parser.elements]}

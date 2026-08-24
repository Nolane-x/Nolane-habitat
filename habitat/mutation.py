from __future__ import annotations

import difflib
import hashlib
import json
import os
import stat
from pathlib import Path

from .model import TransactionRecord
from .policy import canonical_source_path
from .util import sha256_bytes, stable_id, utc_now


class TransactionConflict(RuntimeError):
    pass


class MutationEngine:
    JOURNAL_VERSION = 1

    def __init__(self, workspace):
        self.workspace = workspace

    @staticmethod
    def _valid_rel(rel: str) -> str:
        if not isinstance(rel, str) or not rel:
            raise ValueError("mutation path must be a non-empty string")
        try:
            return canonical_source_path(rel)
        except ValueError as exc:
            raise ValueError("mutation path escapes source root") from exc

    def _normalize_operations(self, operations: list[dict]) -> list[dict]:
        if not isinstance(operations,list) or not operations:
            raise ValueError("operations must be a non-empty list")
        normalized=[]
        structural_paths=set()
        for raw in operations:
            if not isinstance(raw,dict): raise TypeError("each mutation operation must be an object")
            op=dict(raw); kind=op.get("op")
            if kind == "replace_text":
                rel=self._valid_rel(op.get("path")); op["path"]=rel
                if not self.workspace.source_is_file(rel): raise FileNotFoundError(rel)
                op.setdefault("expected_digest",sha256_bytes(self.workspace.read_source_bytes(rel)))
                if not isinstance(op.get("old"),str) or not isinstance(op.get("new"),str): raise ValueError("replace_text requires string old/new")
            elif kind == "replace_span":
                rel=self._valid_rel(op.get("path")); op["path"]=rel
                if not self.workspace.source_is_file(rel): raise FileNotFoundError(rel)
                op.setdefault("expected_digest",sha256_bytes(self.workspace.read_source_bytes(rel)))
                for key in ("start_line","end_line","start_column","end_column"):
                    if not isinstance(op.get(key),int) or isinstance(op.get(key),bool): raise ValueError(f"replace_span requires integer {key}")
                if op["start_line"]!=op["end_line"] or op["start_line"]<1 or op["start_column"]<0 or op["end_column"]<op["start_column"]:
                    raise ValueError("replace_span supports one valid 1-based line with 0-based columns")
                if not isinstance(op.get("expected_text"),str) or not isinstance(op.get("new_text"),str): raise ValueError("replace_span requires expected_text/new_text strings")
            elif kind == "replace_symbol_source":
                sid=op.get("symbol_id")
                if not isinstance(sid,str): raise ValueError("replace_symbol_source requires symbol_id")
                sym=self.workspace.store.symbol_by_id(sid)
                if not sym: raise KeyError(sid)
                if sym["trust"] == "heuristic": raise TransactionConflict("semantic mutation refuses heuristic symbol anchors; inspect exact source and use a safer operation")
                fr=self.workspace.store.file_by_id(sym["file_id"])
                if not fr: raise KeyError(sym["file_id"])
                source=self.workspace.inspect(sid,"body")["source"]
                op.update({"path":sym["path"],"start_line":sym["start_line"],"end_line":sym["end_line"],"expected_digest":fr["digest"],"expected_source":source,"symbol_trust":sym["trust"]})
                if not isinstance(op.get("new_source"),str): raise ValueError("replace_symbol_source requires new_source string")
            elif kind == "create_file":
                rel=self._valid_rel(op.get("path")); op["path"]=rel
                if self.workspace.source_is_file(rel): raise FileExistsError(rel)
                if not isinstance(op.get("content"),str): raise ValueError("create_file requires UTF-8 string content")
                mode=op.get("mode",0o644)
                if not isinstance(mode,int) or isinstance(mode,bool) or mode<0 or mode>0o7777: raise ValueError("create_file mode must be an integer permission mask")
                op["mode"]=mode; structural_paths.add(rel)
            elif kind == "delete_file":
                rel=self._valid_rel(op.get("path")); op["path"]=rel
                if not self.workspace.source_is_file(rel): raise FileNotFoundError(rel)
                op.setdefault("expected_digest",sha256_bytes(self.workspace.read_source_bytes(rel))); structural_paths.add(rel)
            elif kind == "move_file":
                src=self._valid_rel(op.get("from_path")); dst=self._valid_rel(op.get("to_path")); op["from_path"]=src; op["to_path"]=dst
                if not self.workspace.source_is_file(src): raise FileNotFoundError(src)
                if self.workspace.source_is_file(dst): raise FileExistsError(dst)
                op.setdefault("expected_digest",sha256_bytes(self.workspace.read_source_bytes(src))); structural_paths.update({src,dst})
            else:
                raise ValueError(f"unsupported mutation: {kind}")
            normalized.append(op)
        # Structural operations cannot be mixed with text edits of the same path in one transaction.
        for op in normalized:
            if op["op"] in {"replace_text","replace_span","replace_symbol_source"} and op["path"] in structural_paths:
                raise ValueError(f"cannot mix structural and text mutation for {op['path']} in one transaction")
        return normalized

    @staticmethod
    def _newline_style(original: bytes) -> str:
        crlf=original.count(b"\r\n")
        lf=original.count(b"\n")-crlf
        return "\r\n" if crlf>0 and crlf>=lf else "\n"

    def _prepare(self, operations: list[dict]) -> tuple[dict[str,bytes],dict[str,bytes],list[dict]]:
        grouped: dict[str,list[dict]]={}
        structural=[]
        for op in operations:
            if op["op"] in {"replace_text","replace_span","replace_symbol_source"}:
                grouped.setdefault(op["path"],[]).append(op)
            else:
                structural.append(op)
        originals: dict[str,bytes]={}; outputs: dict[str,bytes]={}; previews=[]
        for rel,ops in grouped.items():
            original=self.workspace.read_source_bytes(rel); originals[rel]=original
            expected={o.get("expected_digest") for o in ops if o.get("expected_digest")}
            if len(expected)>1: raise TransactionConflict(f"operations for {rel} were staged against different source digests")
            if expected and sha256_bytes(original) not in expected: raise TransactionConflict(f"stale source digest for {rel}")
            try: text=original.decode("utf-8",errors="strict")
            except UnicodeDecodeError as exc: raise TransactionConflict(f"text mutation requires UTF-8 source: {rel}: {exc}") from exc
            newline=self._newline_style(original); trailing=text.endswith("\n")
            span_ops=sorted((o for o in ops if o["op"]=="replace_span"),key=lambda o:(o["start_line"],o["start_column"]),reverse=True)
            lines=text.splitlines()
            for op in span_ops:
                idx=int(op["start_line"])-1
                if idx<0 or idx>=len(lines): raise TransactionConflict(f"replace_span line out of range for {rel}")
                line=lines[idx]; a=int(op["start_column"]); b=int(op["end_column"]); current=line[a:b]
                if current!=op["expected_text"]: raise TransactionConflict(f"replace_span anchor drifted for {rel}:{op['start_line']}:{a}; expected {op['expected_text']!r}, found {current!r}")
                lines[idx]=line[:a]+op["new_text"]+line[b:]
            text=newline.join(lines)+(newline if trailing else "")
            symbol_ops=sorted((o for o in ops if o["op"]=="replace_symbol_source"),key=lambda o:o["start_line"],reverse=True)
            lines=text.splitlines()
            for op in symbol_ops:
                start,end=int(op["start_line"]),int(op["end_line"])
                current="\n".join(lines[start-1:end])
                expected_source=op["expected_source"].replace("\r\n","\n").replace("\r","\n")
                if current!=expected_source: raise TransactionConflict(f"symbol source changed or anchor drifted for {op['symbol_id']}")
                replacement=op["new_source"].replace("\r\n","\n").replace("\r","\n").splitlines(); lines[start-1:end]=replacement
            text=newline.join(lines)+(newline if trailing else "")
            for op in (o for o in ops if o["op"]=="replace_text"):
                count=text.count(op["old"])
                if count!=1: raise TransactionConflict(f"replace_text requires exactly one match in {rel}; found {count}")
                text=text.replace(op["old"],op["new"],1)
            outputs[rel]=text.encode("utf-8")
            diff="".join(difflib.unified_diff(original.decode("utf-8").splitlines(True),text.splitlines(True),fromfile=f"a/{rel}",tofile=f"b/{rel}",n=3))
            previews.append({"path":rel,"changed":original!=outputs[rel],"unified_diff":diff[:40000],"diff_truncated":len(diff)>40000,"newline_preserved":newline=="\r\n"})
        for op in structural:
            kind=op["op"]
            if kind=="create_file":
                outputs[op["path"]]=op["content"].encode("utf-8")
                previews.append({"path":op["path"],"changed":True,"structural":"create","mode":op["mode"]})
            elif kind=="delete_file":
                raw=self.workspace.read_source_bytes(op["path"]); originals[op["path"]]=raw
                if sha256_bytes(raw)!=op["expected_digest"]: raise TransactionConflict(f"stale source digest for {op['path']}")
                previews.append({"path":op["path"],"changed":True,"structural":"delete"})
            elif kind=="move_file":
                raw=self.workspace.read_source_bytes(op["from_path"]); originals[op["from_path"]]=raw
                if sha256_bytes(raw)!=op["expected_digest"]: raise TransactionConflict(f"stale source digest for {op['from_path']}")
                previews.append({"path":op["from_path"],"to_path":op["to_path"],"changed":True,"structural":"move"})
        return originals,outputs,previews

    def _transaction_dir(self, txid: str) -> Path:
        root = self.workspace.habitat_dir/"transactions"
        safe = root/f"tx-{hashlib.sha256(txid.encode('utf-8')).hexdigest()}"
        legacy = root/txid
        try:
            if Path(txid).name == txid and legacy.is_dir():
                return legacy
        except OSError:
            pass
        return safe

    def _journal_path(self, txid: str) -> Path:
        return self._transaction_dir(txid)/"journal.json"

    def _write_journal(self, txid: str, value: dict) -> None:
        p=self._journal_path(txid); p.parent.mkdir(parents=True,exist_ok=True)
        tmp=p.with_suffix(".tmp")
        with tmp.open("w",encoding="utf-8") as f:
            json.dump(value,f,indent=2,sort_keys=True); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
        if os.name!="nt":
            try:
                fd=os.open(p.parent,os.O_RDONLY); os.fsync(fd); os.close(fd)
            except OSError: pass

    def _load_journal(self, txid: str) -> dict | None:
        p=self._journal_path(txid)
        if not p.is_file(): return None
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: return None

    def _begin_normalized(self, normalized: list[dict]) -> TransactionRecord:
        self.workspace.reconcile()
        base=self.workspace.revision; _,_,preview=self._prepare(normalized)
        txid=stable_id("tx",base,utc_now(),json.dumps(normalized,sort_keys=True))
        tx=TransactionRecord(txid,base,"staged",normalized,preview=preview)
        self.workspace.store.save_json("transactions",tx.id,tx.__dict__)
        return tx

    def begin(self, operations: list[dict]) -> TransactionRecord:
        return self._begin_normalized(self._normalize_operations(operations))

    def load(self, txid: str) -> TransactionRecord:
        value=self.workspace.store.load_json("transactions",txid)
        if not value: raise KeyError(txid)
        return TransactionRecord(**value)

    def _backup(self, tx: TransactionRecord, originals: dict[str,bytes]) -> dict[str,dict]:
        root=self._transaction_dir(tx.id)/"backup"; root.mkdir(parents=True,exist_ok=True)
        meta={}
        for rel,raw in originals.items():
            b=root/rel; b.parent.mkdir(parents=True,exist_ok=True); b.write_bytes(raw)
            try:
                p=self.workspace.resolve_source_path(rel); mode=stat.S_IMODE(p.stat().st_mode) if p.exists() else None
            except Exception: mode=None
            meta[rel]={"existed":True,"mode":mode}
        for op in tx.operations:
            if op["op"]=="create_file": meta.setdefault(op["path"],{"existed":False,"mode":None})
            if op["op"]=="move_file": meta.setdefault(op["to_path"],{"existed":False,"mode":None})
        return meta

    def _restore_from_journal(self, txid: str, journal: dict) -> None:
        backup_root=self._transaction_dir(txid)/"backup"
        meta=journal.get("backup_meta") or {}
        # Remove destinations/new files first, then restore original paths.
        for rel,info in meta.items():
            if not info.get("existed") and self.workspace.source_is_file(rel):
                self.workspace.delete_source_file(rel)
        for rel,info in meta.items():
            if not info.get("existed"): continue
            b=backup_root/rel
            if b.is_file():
                self.workspace.write_source_bytes(rel,b.read_bytes())
                mode=info.get("mode")
                if mode is not None:
                    try: os.chmod(self.workspace.resolve_source_path(rel),int(mode))
                    except OSError: pass
        journal["state"]="rolled-back"; journal["recovered_at"]=utc_now(); self._write_journal(txid,journal)

    def recover_pending(self) -> list[dict]:
        root=self.workspace.habitat_dir/"transactions"
        if not root.is_dir(): return []
        recovered=[]
        for jp in root.glob("*/journal.json"):
            try: journal=json.loads(jp.read_text(encoding="utf-8"))
            except Exception: continue
            if journal.get("state") in {"committed","rolled-back"}: continue
            txid=journal.get("transaction_id")
            if not isinstance(txid,str):
                legacy_txid=jp.parent.name
                txid=legacy_txid if self.workspace.store.load_json("transactions",legacy_txid) else None
            if txid is None:
                continue
            tx=self.workspace.store.load_json("transactions",txid)
            if tx and tx.get("status")=="committed":
                journal["state"]="committed"; journal["recovered_at"]=utc_now(); self._write_journal(txid,journal)
                recovered.append({"transaction_id":txid,"action":"finalized-commit-marker"}); continue
            self._restore_from_journal(txid,journal)
            if tx:
                tx["status"]="rolled-back"; self.workspace.store.save_json("transactions",txid,tx)
            recovered.append({"transaction_id":txid,"action":"rolled-back-incomplete-transaction"})
        if recovered:
            self.workspace.refresh(reason="startup-transaction-recovery")
        return recovered

    def apply(self, tx: TransactionRecord) -> TransactionRecord:
        self.workspace.reconcile()
        current_revision=self.workspace.revision
        # Alpha.10 optimistic rebase: a project-wide revision change does not by itself invalidate
        # a transaction. Exact per-path preconditions below remain authoritative. This lets disjoint
        # agents make progress while still failing closed if any touched source/destination drifted.
        if tx.base_revision!=current_revision:
            for op in tx.operations:
                if op.get("op")=="create_file" and self.workspace.source_is_file(op["path"]):
                    raise TransactionConflict(f"create destination appeared after staging: {op['path']}")
                if op.get("op")=="move_file" and self.workspace.source_is_file(op["to_path"]):
                    raise TransactionConflict(f"move destination appeared after staging: {op['to_path']}")
            tx.rebased_from_revision=tx.base_revision
            tx.rebased_onto_revision=current_revision
        originals,outputs,preview=self._prepare(tx.operations)
        affected=set(outputs)|set(originals)
        for op in tx.operations:
            if op["op"]=="move_file": affected.add(op["to_path"])
        before_symbols={rel:{r["id"] for r in self.workspace.store.all_symbols() if r["path"]==rel} for rel in affected}
        backup_meta=self._backup(tx,originals)
        journal={"version":self.JOURNAL_VERSION,"transaction_id":tx.id,"base_revision":tx.base_revision,"state":"prepared","backup_meta":backup_meta,"applied":[],"created_at":utc_now()}
        self._write_journal(tx.id,journal)
        written=[]
        try:
            journal["state"]="applying"; self._write_journal(tx.id,journal)
            structural=[o for o in tx.operations if o["op"] in {"create_file","delete_file","move_file"}]
            text_paths={o["path"] for o in tx.operations if o["op"] in {"replace_text","replace_span","replace_symbol_source"}}
            # Apply content replacements and creates.
            create_modes={o["path"]:o.get("mode",0o644) for o in structural if o["op"]=="create_file"}
            for rel,data in outputs.items():
                if rel in originals and data==originals[rel]: continue
                self.workspace.write_source_bytes(rel,data); written.append(rel); journal["applied"].append({"op":"write","path":rel}); self._write_journal(tx.id,journal)
                if rel in create_modes:
                    try: os.chmod(self.workspace.resolve_source_path(rel),int(create_modes[rel]))
                    except OSError: pass
            for op in structural:
                if op["op"]=="delete_file":
                    self.workspace.delete_source_file(op["path"]); written.append(op["path"]); journal["applied"].append({"op":"delete","path":op["path"]}); self._write_journal(tx.id,journal)
                elif op["op"]=="move_file":
                    self.workspace.move_source_file(op["from_path"],op["to_path"]); written.extend([op["from_path"],op["to_path"]]); journal["applied"].append({"op":"move","from":op["from_path"],"to":op["to_path"]}); self._write_journal(tx.id,journal)
            self.workspace.refresh_paths(sorted(affected), reason=f"transaction:{tx.id}")
            after_symbols={rel:{r["id"] for r in self.workspace.store.all_symbols() if r["path"]==rel} for rel in affected}
            tx.status="committed"; tx.changed_paths=sorted(set(written)); tx.committed_revision=self.workspace.revision; tx.preview=preview
            tx.semantic_diff={rel:{"added_symbol_ids":sorted(after_symbols.get(rel,set())-before_symbols.get(rel,set())),"removed_symbol_ids":sorted(before_symbols.get(rel,set())-after_symbols.get(rel,set()))} for rel in affected}
            self.workspace.store.save_json("transactions",tx.id,tx.__dict__)
            journal["state"]="committed"; journal["committed_revision"]=tx.committed_revision; journal["committed_at"]=utc_now(); self._write_journal(tx.id,journal)
            return tx
        except Exception:
            self._restore_from_journal(tx.id,journal)
            self.workspace.refresh_paths(sorted(affected), reason=f"failed-transaction-rollback:{tx.id}")
            tx.status="rolled-back"; tx.changed_paths=sorted(set(written)); self.workspace.store.save_json("transactions",tx.id,tx.__dict__)
            raise

    def rollback_committed(self, tx: TransactionRecord) -> TransactionRecord:
        if tx.status == "staged":
            # Cancelling a staged transaction is a pure state transition: no source side effect has
            # occurred yet, so it can be closed without a journal restore.
            tx.status="rolled-back"
            self.workspace.store.save_json("transactions",tx.id,tx.__dict__)
            return tx
        if tx.status!="committed" or not tx.committed_revision: raise TransactionConflict("only staged or committed transactions can be rolled back")
        self.workspace.reconcile()
        if self.workspace.revision!=tx.committed_revision: raise TransactionConflict("workspace changed after commit; automatic rollback would overwrite newer work")
        journal=self._load_journal(tx.id)
        if not journal: raise TransactionConflict("missing transaction journal")
        self._restore_from_journal(tx.id,journal)
        self.workspace.refresh_paths(sorted((journal.get("backup_meta") or {}).keys()), reason=f"explicit-rollback:{tx.id}")
        tx.status="rolled-back"; tx.committed_revision=self.workspace.revision; self.workspace.store.save_json("transactions",tx.id,tx.__dict__)
        return tx

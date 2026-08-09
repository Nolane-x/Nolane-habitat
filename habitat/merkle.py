from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

MERKLE_VERSION = 1


def _hash(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", "surrogatepass")); h.update(b"\0")
    return h.hexdigest()


@dataclass(frozen=True)
class MerkleSnapshot:
    root_hash: str
    nodes: dict[str, dict]
    leaves: dict[str, dict]
    file_count: int
    byte_size: int

    def as_dict(self) -> dict:
        return {
            "version": MERKLE_VERSION, "root_hash": self.root_hash, "nodes": self.nodes,
            "leaves": self.leaves, "file_count": self.file_count, "byte_size": self.byte_size,
        }


def build_snapshot(entries: Iterable[tuple[str, str, int]]) -> MerkleSnapshot:
    """Build a path-sensitive Merkle tree from already-computed file digests.

    This function never opens project files. It turns Habitat's canonical digest inventory into a
    content-addressed directory state so agents/checkpoints can compare subtrees without re-reading bytes.
    """
    leaves: dict[str, dict] = {}
    dirs: dict[str, set[str]] = {"": set()}
    total = 0
    for raw_path, digest, size in sorted(entries):
        path = PurePosixPath(raw_path).as_posix().lstrip("/")
        if not path or path.startswith("../"):
            continue
        parts = PurePosixPath(path).parts
        total += int(size)
        leaf_hash = _hash(["blob", digest, str(int(size))])
        leaves[path] = {"hash": leaf_hash, "content_digest": digest, "size": int(size), "type": "file"}
        parent = ""
        for i, part in enumerate(parts):
            dirs.setdefault(parent, set()).add(part)
            if i < len(parts) - 1:
                parent = "/".join(parts[: i + 1])
                dirs.setdefault(parent, set())

    nodes: dict[str, dict] = {}
    # Compute deepest directories first. Child hashes come either from leaves or previously-computed dirs.
    for d in sorted(dirs, key=lambda x: (x.count("/"), len(x)), reverse=True):
        children = []
        file_count = 0; byte_size = 0
        for name in sorted(dirs[d]):
            child_path = f"{d}/{name}" if d else name
            if child_path in leaves:
                item = leaves[child_path]
                child_hash = item["hash"]; typ = "file"; fc = 1; bs = item["size"]
            else:
                item = nodes.get(child_path)
                if item is None:
                    # Empty directory is not represented by source inventory and therefore omitted.
                    continue
                child_hash = item["hash"]; typ = "tree"; fc = item["file_count"]; bs = item["byte_size"]
            children.append({"name": name, "type": typ, "hash": child_hash})
            file_count += fc; byte_size += bs
        tree_hash = _hash(["tree", *[f"{c['name']}:{c['type']}:{c['hash']}" for c in children]])
        nodes[d] = {"hash": tree_hash, "type": "tree", "children": children, "file_count": file_count, "byte_size": byte_size}
    root = nodes.get("", {"hash": _hash(["tree"]), "file_count": 0, "byte_size": 0})
    return MerkleSnapshot(root["hash"], nodes, leaves, len(leaves), total)


def subtree(snapshot: dict, prefix: str = "") -> dict | None:
    prefix = PurePosixPath(prefix).as_posix().strip("/") if prefix else ""
    if prefix in snapshot.get("leaves", {}):
        return {"path": prefix, **snapshot["leaves"][prefix]}
    node = snapshot.get("nodes", {}).get(prefix)
    return {"path": prefix, **node} if node else None


def diff_snapshots(old: dict, new: dict, prefix: str = "") -> dict:
    prefix = PurePosixPath(prefix).as_posix().strip("/") if prefix else ""
    old_leaves = old.get("leaves", {}); new_leaves = new.get("leaves", {})
    if prefix:
        key = prefix.rstrip("/") + "/"
        old_leaves = {p: v for p, v in old_leaves.items() if p == prefix or p.startswith(key)}
        new_leaves = {p: v for p, v in new_leaves.items() if p == prefix or p.startswith(key)}
    old_paths = set(old_leaves); new_paths = set(new_leaves)
    added = sorted(new_paths - old_paths); deleted = sorted(old_paths - new_paths)
    modified = sorted(p for p in old_paths & new_paths if old_leaves[p].get("content_digest") != new_leaves[p].get("content_digest"))
    # Detect exact-content moves/renames as a derived convenience signal. One digest may appear many times;
    # only one-to-one pairs are promoted as a rename to avoid false certainty.
    old_by_digest: dict[str, list[str]] = {}; new_by_digest: dict[str, list[str]] = {}
    for p in deleted: old_by_digest.setdefault(old_leaves[p].get("content_digest"), []).append(p)
    for p in added: new_by_digest.setdefault(new_leaves[p].get("content_digest"), []).append(p)
    renamed = []
    for digest, olds in old_by_digest.items():
        news = new_by_digest.get(digest, [])
        if digest and len(olds) == len(news) == 1:
            renamed.append({"from": olds[0], "to": news[0], "content_digest": digest, "trust": "exact"})
    return {
        "prefix": prefix, "old_root": old.get("root_hash"), "new_root": new.get("root_hash"),
        "added": added, "deleted": deleted, "modified": modified, "renamed": renamed,
        "changed": bool(added or deleted or modified),
    }


def resolve_store_path(store, root_hash: str, prefix: str = "") -> dict | None:
    """Resolve a path through content-addressed tree objects."""
    parts = [p for p in PurePosixPath(prefix).parts if p not in {"", "."}] if prefix else []
    current_hash = root_hash
    current = store.merkle_object(current_hash)
    if current is None:
        return None
    path_parts: list[str] = []
    for part in parts:
        if current.get("kind") != "tree":
            return None
        child = next((c for c in current.get("children", []) if c.get("name") == part), None)
        if child is None:
            return None
        current_hash = child["hash"]; current = store.merkle_object(current_hash)
        if current is None:
            return None
        path_parts.append(part)
    return {"path": "/".join(path_parts), **current}


def _walk_store(store, object_hash: str, prefix: str = "") -> dict[str, dict]:
    obj = store.merkle_object(object_hash)
    if not obj:
        return {}
    if obj.get("kind") == "file":
        return {prefix: obj}
    out: dict[str, dict] = {}
    for child in obj.get("children", []):
        path = f"{prefix}/{child['name']}" if prefix else child["name"]
        out.update(_walk_store(store, child["hash"], path))
    return out


def diff_store_roots(store, old_root: str, new_root: str, prefix: str = "") -> dict:
    """Merkle-pruned diff. Equal subtree hashes are skipped without enumerating their leaves."""
    old_node = resolve_store_path(store, old_root, prefix)
    new_node = resolve_store_path(store, new_root, prefix)
    old_hash = old_node.get("hash") if old_node else None; new_hash = new_node.get("hash") if new_node else None
    if old_hash == new_hash and old_hash:
        return {"prefix": prefix, "old_root": old_hash, "new_root": new_hash, "added": [], "deleted": [], "modified": [], "renamed": [], "changed": False, "pruned_equal_subtree": True}
    old_leaves = _walk_store(store, old_hash, prefix) if old_hash else {}
    new_leaves = _walk_store(store, new_hash, prefix) if new_hash else {}
    old_paths=set(old_leaves); new_paths=set(new_leaves)
    added=sorted(new_paths-old_paths); deleted=sorted(old_paths-new_paths)
    modified=sorted(p for p in old_paths & new_paths if old_leaves[p].get("content_digest") != new_leaves[p].get("content_digest"))
    old_by: dict[str,list[str]]={}; new_by: dict[str,list[str]]={}
    for p in deleted: old_by.setdefault(old_leaves[p].get("content_digest"),[]).append(p)
    for p in added: new_by.setdefault(new_leaves[p].get("content_digest"),[]).append(p)
    renamed=[]
    for digest, olds in old_by.items():
        news=new_by.get(digest,[])
        if digest and len(olds)==len(news)==1:
            renamed.append({"from":olds[0],"to":news[0],"content_digest":digest,"trust":"exact"})
    return {"prefix":prefix,"old_root":old_hash,"new_root":new_hash,"added":added,"deleted":deleted,"modified":modified,"renamed":renamed,"changed":bool(added or deleted or modified),"pruned_equal_subtree":False}

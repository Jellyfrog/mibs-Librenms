from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .aliases import resolve_module
from .discover import EXTERNAL_DIR, ROOT_DIR
from .model import Module, Obj
from .parse_regex import WELL_KNOWN


def oid_key(oid: str) -> tuple[int, ...]:
    return tuple(int(x) for x in oid.split(".") if x.isdigit())


@dataclass
class Node:
    obj: Obj
    children: list["Node"] = field(default_factory=list)


def build_tree(objs: list[Obj]) -> list[Node]:
    nodes: dict[str, Node] = {}
    roots: list[Node] = []

    def container(oid: str) -> list[Node]:
        arcs = oid.split(".")
        for i in range(len(arcs) - 1, 0, -1):
            parent = nodes.get(".".join(arcs[:i]))
            if parent:
                return parent.children
        return roots

    for o in sorted((o for o in objs if o.oid), key=lambda o: oid_key(o.oid)):
        if o.oid in nodes:  # another name for the same OID: a sibling row, so its #name anchor exists
            container(o.oid).append(Node(o))
            continue
        nodes[o.oid] = Node(o)
        container(o.oid).append(nodes[o.oid])
    return roots


class SymbolTable:
    def __init__(self, modules: list[Module]):
        self.modules: dict[str, Module] = {m.id: m for m in modules}
        self._by_modname: dict[str, list[Module]] = defaultdict(list)
        for m in modules:
            self._by_modname[m.name].append(m)
        self._names = set(self._by_modname)
        self.by_oid: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        self.by_name: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.imported_by: dict[str, list[str]] = defaultdict(list)
        self._resolve_pending()
        self._index()

    def resolve_module(self, importer: Module, name: str) -> Module | None:
        cands = self._by_modname.get(resolve_module(name, self._names), [])
        for pref in (importer.dir, ROOT_DIR, EXTERNAL_DIR):
            for c in cands:
                if c.dir == pref:
                    return c
        return cands[0] if cands else None

    def _lookup(self, mod: Module, symbol: str) -> str | None:
        for o in mod.objects:
            if o.name == symbol and o.oid:
                return o.oid
        for modname, syms in mod.imports.items():
            if symbol in syms:
                src = self.resolve_module(mod, modname)
                if src is not None and src is not mod:
                    for o in src.objects:
                        if o.name == symbol and o.oid:
                            return o.oid
        return WELL_KNOWN.get(symbol)

    def _resolve_pending(self) -> None:
        for _ in range(10):
            progress = False
            for mod in self.modules.values():
                for o in mod.objects:
                    if o.oid is None and o.parent_ref:
                        base = self._lookup(mod, o.parent_ref[0])
                        if base:
                            o.oid, o.parent_ref = f"{base}.{o.parent_ref[1]}", None
                            progress = True
            if not progress:
                return

    def _index(self) -> None:
        for mod in self.modules.values():
            mid = mod.id
            for o in mod.objects:
                if o.oid:
                    self.by_oid[o.oid].append((mid, o.name, o.kind))
                    self.by_name[o.name].append((mid, o.oid))
            for modname in mod.imports:
                src = self.resolve_module(mod, modname)
                if src is not None and src is not mod and mid not in self.imported_by[src.id]:
                    self.imported_by[src.id].append(mid)

    def longest_prefix(self, oid: str) -> tuple[str, list[tuple[str, str, str]]] | None:
        arcs = oid.strip(".").split(".")
        for i in range(len(arcs), 0, -1):
            key = ".".join(arcs[:i])
            if key in self.by_oid:
                return key, self.by_oid[key]
        return None

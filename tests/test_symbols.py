from mibsite.model import Module, Obj
from mibsite.symbols import SymbolTable, build_tree


def _mods():
    smi = Module("SNMPv2-SMI", "_root", "SNMPv2-SMI", "netsnmp", objects=[Obj("enterprises", "1.3.6.1.4.1", "node")])
    a_root = Module("A-MIB", "_root", "A-MIB", "pysmi", objects=[Obj("aRoot", "1.3.6.1.4.1.5", "node")])
    a_vendor = Module("A-MIB", "acme", "acme/A-MIB", "pysmi", objects=[Obj("aRoot", "1.3.6.1.4.1.6", "node")])
    b = Module("B-MIB", "acme", "acme/B-MIB", "regex", imports={"A-MIB": ["aRoot"], "RFC-1213": ["ifIndex"]},
               objects=[Obj("bTab", None, "node", parent_ref=("aRoot", 2)),
                        Obj("bCol", None, "column", parent_ref=("bTab", 1))])
    r1213 = Module("RFC1213-MIB", "_root", "RFC1213-MIB", "pysmi")
    return [smi, a_root, a_vendor, b, r1213]


def test_resolve_module_prefers_own_dir():
    t = SymbolTable(_mods())
    b = t.modules["acme/B-MIB"]
    assert t.resolve_module(b, "A-MIB").id == "acme/A-MIB"
    assert t.resolve_module(t.modules["_root/SNMPv2-SMI"], "A-MIB").id == "_root/A-MIB"
    assert t.resolve_module(b, "RFC-1213").id == "_root/RFC1213-MIB"
    assert t.resolve_module(b, "NOPE") is None


def test_pending_resolution_uses_imports():
    t = SymbolTable(_mods())
    objs = {o.name: o.oid for o in t.modules["acme/B-MIB"].objects}
    assert objs == {"bTab": "1.3.6.1.4.1.6.2", "bCol": "1.3.6.1.4.1.6.2.1"}


def test_indexes_and_lookup():
    t = SymbolTable(_mods())
    assert t.by_name["aRoot"] == [("_root/A-MIB", "1.3.6.1.4.1.5"), ("acme/A-MIB", "1.3.6.1.4.1.6")]
    oid, entries = t.longest_prefix("1.3.6.1.4.1.6.2.1.7.0")
    assert oid == "1.3.6.1.4.1.6.2.1" and entries == [("acme/B-MIB", "bCol", "column")]
    assert t.longest_prefix("9.9") is None
    assert t.imported_by["acme/A-MIB"] == ["acme/B-MIB"]
    assert t.imported_by["_root/RFC1213-MIB"] == ["acme/B-MIB"]


def test_build_tree():
    objs = [Obj("c", "1.2.3", "scalar"), Obj("a", "1.2", "node"), Obj("x", "1.10", "node"),
            Obj("b", "1.2.10", "scalar"), Obj("z", None, "node")]
    roots = build_tree(objs)
    assert [n.obj.name for n in roots] == ["a", "x"]
    assert [n.obj.name for n in roots[0].children] == ["c", "b"]


def test_objects_sharing_an_oid_become_sibling_rows():
    from mibsite.model import Obj
    from mibsite.symbols import build_tree
    [root] = build_tree([Obj("rnd", "1.3.6.1.4.1.9.6", "node"), Obj("leaf", "1.3.6.1.4.1.9.6.1", "scalar"),
                         Obj("alias", "1.3.6.1.4.1.9.6.1", "node")])
    assert [c.obj.name for c in root.children] == ["leaf", "alias"]

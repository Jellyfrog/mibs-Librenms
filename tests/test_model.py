from mibsite.model import Module, Obj, TextualConvention


def test_roundtrip():
    m = Module("X-MIB", "_root", "X-MIB", "pysmi", errors=["e"], imports={"A": ["b"]},
               identity={"organization": "o", "revisions": []},
               objects=[Obj("x", "1.3", "scalar", enums={"a": 1}, parent_ref=("p", 2))],
               tcs=[TextualConvention("T", "INTEGER")])
    assert m.id == "_root/X-MIB" and m.url == "/mib/X-MIB/" and m.label == "X-MIB"
    assert Module("Y-MIB", "cisco", "cisco/Y-MIB", "pysmi").url == "/mib/cisco/Y-MIB/"
    assert Module.from_dict(m.to_dict()) == m

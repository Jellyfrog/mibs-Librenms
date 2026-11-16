from mibsite.model import Module, Obj
from mibsite.snmprec import decode_value, humanize_ticks, collect_examples
from mibsite.symbols import SymbolTable


def test_decode():
    assert decode_value("4", "hello") == ("OCTET STRING", "hello")
    assert decode_value("4x", "7769646765742d32") == ("OCTET STRING", "widget-2")
    assert decode_value("4x", "0011aabb") == ("OCTET STRING", "00:11:aa:bb")
    assert decode_value("64x", "c0a80001") == ("IpAddress", "192.168.0.1")
    assert decode_value("67", "8640000") == ("TimeTicks", "8640000 (1d 0h 0m 0s)")
    assert decode_value("65", "5") == ("Counter32", "5")
    assert decode_value("4x", "zz") == ("OCTET STRING", "zz")


def test_humanize():
    assert humanize_ticks(366100) == "0d 1h 1m 1s"


def test_collect(fixtures_dir):
    m = Module("GOOD-MIB", "_root", "GOOD-MIB", "pysmi", objects=[
        Obj("goodName", "1.3.6.1.4.1.99999.1.1", "scalar"),
        Obj("goodEntry", "1.3.6.1.4.1.99999.1.2.1", "row"),
        Obj("goodState", "1.3.6.1.4.1.99999.1.2.1.2", "column"),
        Obj("goodOctets", "1.3.6.1.4.1.99999.1.2.1.3", "column"),
    ])
    ex = collect_examples(fixtures_dir / "snmpsim", SymbolTable([m]))["_root/GOOD-MIB"]
    assert [e["v"] for e in ex["goodName"]] == ["widget-1", "widget-2"]
    assert ex["goodName"][0] == {"v": "widget-1", "t": "OCTET STRING", "i": "0", "f": "acme_v1"}
    assert ex["goodState"][0]["i"] == "5"
    assert "goodEntry" not in ex

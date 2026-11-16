import json
from mibsite.model import Module, Obj
from mibsite.search_index import extend_chars, extend_arcs, build_shards, shard_filename, write_search_index


def test_extend():
    assert extend_chars("ifindex", "if") == "ifi"
    assert extend_chars("if", "if") is None
    assert extend_arcs("1.3.6.1", "") == "1"
    assert extend_arcs("1.3.6.1", "1.3") == "1.3.6"
    assert extend_arcs("1.3", "1.3") is None


def test_build_shards_splits_and_covers_all():
    entries = [(k, [k], len(k) + 1) for k in [f"if{i:04d}" for i in range(2000)] + ["ip", "i"]]
    shards = build_shards(entries, extend_chars, max_bytes=2000)
    assert all(sum(len(r[0]) + 1 for r in v) <= 2000 for k, v in shards.items() if len(k) < 24)
    rows = sorted(r[0] for v in shards.values() for r in v)
    assert rows == sorted(k for k, _, _ in entries)
    assert ["i"] in shards["i"]
    for prefix, rows_ in shards.items():
        assert all(r[0].startswith(prefix) for r in rows_)


def test_shard_filename():
    assert shard_filename("") == "_" and shard_filename("1.3.6") == "1.3.6" and shard_filename("if") == "if"


def test_front_code_round_trip():
    from mibsite.search_index import front_code
    items = ["", "1", "1.3", "1.3.6.1.2", "1.3.6.1.4", "if", "ifi"]
    assert front_code(items).split("\n")[:4] == ["0 ", "0 1", "1 .3", "3 .6.1.2"]


def test_write_search_index(tmp_path):
    a = Module("IF-MIB", "_root", "IF-MIB", "pysmi", objects=[Obj("ifInOctets", "1.3.6.1.2.1.2.2.1.10", "column")])
    b = Module("RFC1213-MIB", "_root", "RFC1213-MIB", "pysmi", objects=[Obj("ifInOctets", "1.3.6.1.2.1.2.2.1.10", "column")])
    man = write_search_index(tmp_path, [a, b], {"_root/IF-MIB": "Standards (IETF)"}, max_bytes=50_000)
    assert man["v"] == 2 and man["dirs"] == ["_root"]
    assert man["modules"] == [["IF-MIB", 0, 1], ["RFC1213-MIB", 0, 0]] and man["vendors"] == ["", "Standards (IETF)"]
    assert json.loads((tmp_path / "manifest.json").read_text()) == man
    names = (tmp_path / "n" / "_.txt").read_text().splitlines()
    assert "ifInOctets\t1.3.6.1.2.1.2.2.1.10\t0,1" in names  # same object in two MIBs = one row
    assert "IF-MIB\t\t0" in names
    assert (tmp_path / "o" / "_.txt").read_text() == "1.3.6.1.2.1.2.2.1.10\tifInOctets\t0,1\n"


def test_oid_shards_store_relative_oids(tmp_path):
    objs = [Obj(f"o{i}", f"1.3.6.1.4.1.9.{i}", "scalar") for i in range(400)]
    write_search_index(tmp_path, [Module("BIG-MIB", "x", "x/BIG-MIB", "pysmi", objects=objs)], {}, max_bytes=2_000)
    sub = [f for f in (tmp_path / "o").iterdir() if f.stem.startswith("1.3.6.1.4.1.9")]
    assert sub, "expected deeper OID shards"
    for f in sub:
        for line in f.read_text().splitlines():
            assert not line.startswith("1.3.6"), line  # stored relative to the shard prefix


def test_shards_respect_the_byte_budget(tmp_path):
    objs = [Obj(f"obj{i:05d}Name", f"1.3.6.1.4.1.9.{i // 50}.{i % 50}", "scalar") for i in range(6000)]
    objs.append(Obj("nineNode", "1.3.6.1.4.1.9", "node"))
    budget = 4_000
    write_search_index(tmp_path, [Module("BIG-MIB", "acme", "acme/BIG-MIB", "pysmi", objects=objs)], {}, max_bytes=budget)
    for sub in ("n", "o"):
        files = list((tmp_path / sub).iterdir())
        assert len(files) > 5
        for f in files:
            assert len(f.read_text().encode()) <= budget, f.name

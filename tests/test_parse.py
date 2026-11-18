import json
import pytest
from mibsite.discover import discover, all_dirs, search_dirs
from mibsite.parse import parse_file, parse_all

from conftest import needs_netsnmp


def _files(fixtures_dir, *rels):
    root = fixtures_dir / "mibs"
    return root, [f for f in discover(root, None) if f.rel in rels]


def _parse(root, rel):
    files = discover(root, None)
    mf = next(f for f in files if f.rel == rel)
    available = {m for f in files for m in f.modules}
    return parse_file(mf, search_dirs(mf, root, None, all_dirs(root)), available)


def test_good_uses_pysmi(fixtures_dir):
    [m] = _parse(fixtures_dir / "mibs", "GOOD-MIB")
    assert m.tier == "pysmi" and m.errors == []


def test_missing_import_reported(fixtures_dir):
    [m] = _parse(fixtures_dir / "mibs", "acme/BROKEN-IMPORT-MIB")
    assert m.tier == "pysmi"
    assert m.errors == ["missing dependency: NONEXISTENT-MIB"]
    assert {o.name: o.oid for o in m.objects}["acmeTemp"] == "1.3.6.1.4.1.99998.1"


def test_not_a_mib_is_raw(fixtures_dir):
    [m] = _parse(fixtures_dir / "mibs", "acme/NOT-A-MIB")
    assert m.tier == "raw" and m.name == "NOT-A-MIB" and m.objects == []


@needs_netsnmp
def test_two_modules(fixtures_dir):
    mods = _parse(fixtures_dir / "mibs", "acme/TWO-MODULES")
    assert [m.name for m in mods] == ["FIRST-MIB", "SECOND-MIB"]
    assert all(m.tier != "pysmi" for m in mods)
    assert mods[0].objects[0].oid == "1.3.6.1.4.1.99997"


def test_bad_grammar_falls_to_regex(tmp_path):
    (tmp_path / "BAD-MIB").write_text(
        "BAD-MIB DEFINITIONS ::= BEGIN\nbadRoot OBJECT IDENTIFIER ::= { enterprises 99996 }\n"
        "badThing OBJECT-TYPE\n SYNTAX ??? !!\n ::= { badRoot 1 }\n")
    [m] = _parse(tmp_path, "BAD-MIB")
    assert m.tier in ("netsnmp", "regex")
    assert m.errors and m.errors[0].startswith("pysmi")
    assert {o.name: o.oid for o in m.objects}["badRoot"] == "1.3.6.1.4.1.99996"


def test_parse_all_cache(fixtures_dir, tmp_path):
    root, files = _files(fixtures_dir, "GOOD-MIB", "acme/NOT-A-MIB")
    first = parse_all(files, root, None, jobs=2, cache_dir=tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 2
    second = parse_all(files, root, None, jobs=2, cache_dir=tmp_path)
    assert [m.to_dict() for m in first] == [m.to_dict() for m in second]


@needs_netsnmp
def test_file_too_big_for_pysmi_goes_to_netsnmp(fixtures_dir, monkeypatch):
    import mibsite.parse as parse
    monkeypatch.setattr(parse, "PYSMI_MAX_BYTES", 10)
    monkeypatch.setattr(parse, "compile_pysmi", lambda *a: pytest.fail("pysmi must be skipped"))
    [m] = _parse(fixtures_dir / "mibs", "GOOD-MIB")
    assert m.tier == "netsnmp" and m.errors[0].startswith("pysmi skipped: file is")


def test_cache_keys_change_for_edited_file_and_its_importers(tmp_path):
    from mibsite.parse import cache_keys
    (tmp_path / "BASE-MIB").write_text("BASE-MIB DEFINITIONS ::= BEGIN\nb OBJECT IDENTIFIER ::= { enterprises 1 }\nEND\n")
    (tmp_path / "USER-MIB").write_text("USER-MIB DEFINITIONS ::= BEGIN\nIMPORTS b FROM BASE-MIB x FROM LATER-MIB;\n"
                                       "u OBJECT IDENTIFIER ::= { b 1 }\nEND\n")
    (tmp_path / "OTHER-MIB").write_text("OTHER-MIB DEFINITIONS ::= BEGIN\no OBJECT IDENTIFIER ::= { enterprises 3 }\nEND\n")

    def keys():
        files = discover(tmp_path, None)
        return {rel: k for (_, rel), k in cache_keys(files, {m for f in files for m in f.modules}).items()}

    before = keys()
    (tmp_path / "BASE-MIB").write_text("BASE-MIB DEFINITIONS ::= BEGIN\nb OBJECT IDENTIFIER ::= { enterprises 1 }\n-- edit\nEND\n")
    after = keys()
    # fixing a MIB can make its importers parse, so they are re-parsed too; unrelated files are not
    assert after["BASE-MIB"] != before["BASE-MIB"] and after["USER-MIB"] != before["USER-MIB"]
    assert after["OTHER-MIB"] == before["OTHER-MIB"]
    # a previously missing import appearing re-parses the importer
    (tmp_path / "LATER-MIB").write_text("LATER-MIB DEFINITIONS ::= BEGIN\nx OBJECT IDENTIFIER ::= { enterprises 2 }\nEND\n")
    final = keys()
    assert final["USER-MIB"] != after["USER-MIB"] and final["BASE-MIB"] == after["BASE-MIB"]


def test_damaged_cache_entry_is_reparsed(fixtures_dir, tmp_path):
    root, files = _files(fixtures_dir, "GOOD-MIB")
    [first] = parse_all(files, root, None, jobs=1, cache_dir=tmp_path)
    [entry] = tmp_path.glob("*.json")
    entry.write_text('[{"name": "GOOD')  # truncated write
    [again] = parse_all(files, root, None, jobs=1, cache_dir=tmp_path)
    assert again.to_dict() == first.to_dict()
    assert json.loads(entry.read_text())  # repaired
    assert not list(tmp_path.glob("*.tmp"))


def test_internal_errors_are_not_cached(fixtures_dir, monkeypatch):
    # _work runs in-process here: a monkeypatch would not reach pool workers under forkserver/spawn
    import mibsite.parse as parse
    root, [mf] = _files(fixtures_dir, "GOOD-MIB")
    parse._init(root, None, all_dirs(root), set(mf.modules))
    monkeypatch.setattr(parse, "parse_file", lambda *a: (_ for _ in ()).throw(OSError("transient")))
    fid, [data], cacheable = parse._work(mf)
    assert data["tier"] == "raw" and data["errors"][0].startswith("internal error") and cacheable is False

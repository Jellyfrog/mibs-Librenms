from mibsite.discover import all_dirs
from mibsite.parse_pysmi import compile_pysmi, normalize_pysmi, format_syntax


def _dirs(fixtures_dir):
    root = fixtures_dir / "mibs"
    return all_dirs(root)  # already includes root


def test_format_syntax():
    assert format_syntax({"type": "Integer32", "constraints": {"range": [{"min": 1, "max": 10}]}}) == ("Integer32 (1..10)", None)
    assert format_syntax({"type": "OCTET STRING", "constraints": {"size": [{"min": 0, "max": 64}]}}) == ("OCTET STRING (SIZE (0..64))", None)
    assert format_syntax({"type": "INTEGER", "constraints": {"enumeration": {"up": 1}}}) == ("INTEGER", {"up": 1})
    assert format_syntax(None) == (None, None)


def test_good_mib(fixtures_dir):
    js, msgs = compile_pysmi("GOOD-MIB", _dirs(fixtures_dir), {"GOOD-MIB", "SNMPv2-SMI", "SNMPv2-TC"})
    assert js is not None and msgs == [], msgs
    m = normalize_pysmi(js, "GOOD-MIB", "_root", "GOOD-MIB")
    objs = {o.name: o for o in m.objects}
    assert m.tier == "pysmi"
    assert m.identity["organization"] == "Example Org"
    assert m.identity["revisions"][0]["description"] == "Initial version."
    assert objs["goodMIB"].oid == "1.3.6.1.4.1.99999" and objs["goodMIB"].kind == "identity"
    assert objs["goodTable"].kind == "table"
    assert objs["goodEntry"].kind == "row" and objs["goodEntry"].indexes == ["goodIndex"]
    assert objs["goodOctets"].kind == "column" and objs["goodOctets"].units == "octets"
    assert objs["goodName"].syntax.startswith("DisplayString")
    assert objs["goodStateChange"].kind == "notification" and objs["goodStateChange"].objects == ["goodState"]
    assert objs["goodObjects"].kind == "node"
    assert [t.name for t in m.tcs] == ["GoodState"] and m.tcs[0].enums == {"ok": 1, "failed": 2}
    assert "SNMPv2-SMI" in m.imports


def test_missing_import_tolerated_with_warning(fixtures_dir):
    js, msgs = compile_pysmi("BROKEN-IMPORT-MIB", _dirs(fixtures_dir), {"BROKEN-IMPORT-MIB", "SNMPv2-SMI"})
    assert js is not None and js["acmeTemp"]["oid"] == "1.3.6.1.4.1.99998.1"
    assert msgs == ["missing dependency: NONEXISTENT-MIB"]


def test_bad_grammar_fails(tmp_path):
    (tmp_path / "BAD-MIB").write_text("BAD-MIB DEFINITIONS ::= BEGIN\nfoo OBJECT-TYPE garbage ::= {\nEND\n")
    js, msgs = compile_pysmi("BAD-MIB", [tmp_path], {"BAD-MIB"})
    assert js is None and msgs and msgs[0].startswith("pysmi")


def test_duplicate_definitions_compile_and_keep_their_name(fixtures_dir, tmp_path):
    import shutil
    for base in ("SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF"):
        shutil.copy(fixtures_dir / "mibs" / base, tmp_path / base)
    (tmp_path / "DUP-MIB").write_text(
        "DUP-MIB DEFINITIONS ::= BEGIN\nIMPORTS enterprises FROM SNMPv2-SMI;\n"
        "fw OBJECT IDENTIFIER ::= { enterprises 77 }\nUSG OBJECT IDENTIFIER ::= { fw 284 }\n"
        "USG OBJECT IDENTIFIER ::= { fw 402 }\nother OBJECT IDENTIFIER ::= { fw 5 }\nEND\n")
    js, msgs = compile_pysmi("DUP-MIB", [tmp_path], {"SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF", "DUP-MIB"})
    assert js is not None and msgs == ["defined more than once: USG"]
    mod = normalize_pysmi(js, "DUP-MIB", "_root", "DUP-MIB")
    usg = sorted((o.oid, o.defined_twice) for o in mod.objects if o.name == "USG")
    assert usg == [("1.3.6.1.4.1.77.284", True), ("1.3.6.1.4.1.77.402", True)]
    assert not next(o for o in mod.objects if o.name == "other").defined_twice


def test_underscored_names_compile_and_keep_their_name(fixtures_dir, tmp_path):
    import shutil
    for base in ("SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF"):
        shutil.copy(fixtures_dir / "mibs" / base, tmp_path / base)
    (tmp_path / "US-MIB").write_text(
        "US-MIB DEFINITIONS ::= BEGIN\nIMPORTS OBJECT-TYPE, Counter64, enterprises FROM SNMPv2-SMI;\n"
        "zs OBJECT IDENTIFIER ::= { enterprises 46262 }\n"
        "sme_ca_state OBJECT-TYPE\n SYNTAX Counter64\n MAX-ACCESS read-only\n STATUS current\n"
        " DESCRIPTION \"health_state\"\n ::= { zs 1 }\nEND\n")
    js, msgs = compile_pysmi("US-MIB", [tmp_path], {"SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF", "US-MIB"})
    assert js is not None, msgs
    [o] = [o for o in normalize_pysmi(js, "US-MIB", "_root", "US-MIB").objects if o.oid == "1.3.6.1.4.1.46262.1"]
    assert (o.name, o.syntax, o.access, o.description) == ("sme_ca_state", "Counter64", "read-only", "health_state")


def test_module_named_with_underscores(fixtures_dir, tmp_path):
    import shutil
    for base in ("SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF"):
        shutil.copy(fixtures_dir / "mibs" / base, tmp_path / base)
    (tmp_path / "AH_TRAP_MIB").write_text(
        "AH_TRAP_MIB DEFINITIONS ::= BEGIN\nIMPORTS enterprises FROM SNMPv2-SMI;\n"
        "ahTrap OBJECT IDENTIFIER ::= { enterprises 26928 }\nEND\n")
    js, msgs = compile_pysmi("AH_TRAP_MIB", [tmp_path], {"SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF", "AH_TRAP_MIB"})
    assert js is not None, msgs
    assert [o.name for o in normalize_pysmi(js, "AH_TRAP_MIB", "_root", "AH_TRAP_MIB").objects] == ["ahTrap"]

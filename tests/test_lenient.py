import re

from mibsite.asn1text import parse_imports
from mibsite.lenient import (LM_MARK, UC_MARK, US_MARK, mark_module_names, add_missing_standard_imports, enum_on_integer32, fix_enum_syntax, mark_capitalised_values,
                             mark_lowercase_types,
                             mark_underscores, rename_duplicate_definitions, unmark)

HEAD = "X-MIB DEFINITIONS ::= BEGIN\n"


def test_adds_missing_symbol_to_existing_from():
    t = HEAD + "IMPORTS MODULE-IDENTITY, OBJECT-TYPE FROM SNMPv2-SMI;\nc OBJECT-TYPE SYNTAX Counter64 ::= { x 1 }\nEND\n"
    out = add_missing_standard_imports(t)
    assert set(parse_imports(out)["SNMPv2-SMI"]) == {"MODULE-IDENTITY", "OBJECT-TYPE", "Counter64"}


def test_adds_new_from_clause_and_ignores_strings_and_definitions():
    t = (HEAD + "IMPORTS OBJECT-TYPE FROM SNMPv2-SMI;\n"
         "d OBJECT-TYPE SYNTAX DisplayString DESCRIPTION \"a RowStatus mention\" ::= { x 1 }\n"
         "TimeStamp ::= INTEGER\nt OBJECT-TYPE SYNTAX TimeStamp ::= { x 2 }\nEND\n")
    imports = parse_imports(add_missing_standard_imports(t))
    assert imports["SNMPv2-TC"] == ["DisplayString"]  # not RowStatus (string) nor TimeStamp (defined here)


def test_leaves_smiv1_and_complete_modules_alone():
    v1 = HEAD + "IMPORTS Counter FROM RFC1155-SMI OBJECT-TYPE FROM RFC-1212;\nc OBJECT-TYPE SYNTAX Gauge32 ::= { x 1 }\nEND\n"
    assert add_missing_standard_imports(v1) == v1
    ok = HEAD + "IMPORTS OBJECT-TYPE, Counter64 FROM SNMPv2-SMI;\nc OBJECT-TYPE SYNTAX Counter64 ::= { x 1 }\nEND\n"
    assert add_missing_standard_imports(ok) == ok


def test_module_without_imports_clause():
    t = HEAD + "m MODULE-IDENTITY LAST-UPDATED \"x\" ::= { enterprises 1 }\nEND\n"
    imports = parse_imports(add_missing_standard_imports(t))
    assert set(imports["SNMPv2-SMI"]) == {"MODULE-IDENTITY", "enterprises"}


def test_renames_later_duplicate_definitions():
    t = (HEAD + "IMPORTS enterprises FROM SNMPv2-SMI;\n"
         "fw OBJECT IDENTIFIER ::= { enterprises 1 }\n"
         "USG OBJECT IDENTIFIER ::= { fw 284 }\n"
         "other OBJECT IDENTIFIER ::= { fw 5 }\n"
         "USG OBJECT IDENTIFIER ::= { fw 402 }\n"
         "last OBJECT IDENTIFIER ::= { fw 9 }\nEND\n")
    out, renamed = rename_duplicate_definitions(t)
    assert renamed == ["USG"]
    assert "USG OBJECT IDENTIFIER ::= { fw 284 }" in out
    assert "USG-mibsiteDup2 OBJECT IDENTIFIER ::= { fw 402 }" in out and "fw 9" in out


def test_duplicate_detection_ignores_descriptions_and_clean_modules():
    t = (HEAD + "a OBJECT-TYPE SYNTAX INTEGER DESCRIPTION \"\nb OBJECT IDENTIFIER ::= { x }\" ::= { x 1 }\n"
         "b OBJECT IDENTIFIER ::= { x 2 }\nEND\n")
    assert rename_duplicate_definitions(t) == (t, [])


def test_sequence_members_and_syntax_clauses_are_not_definitions():
    t = (HEAD + "XEntry ::= SEQUENCE { xSpecific OBJECT IDENTIFIER }\n"
         "xSpecific OBJECT-TYPE\n SYNTAX OBJECT IDENTIFIER\n ::= { x 1 }\n"
         "y OBJECT-TYPE\n SYNTAX OBJECT IDENTIFIER\n ::= { x 2 }\nEND\n")
    assert rename_duplicate_definitions(t) == (t, [])


def test_underscores_are_marked_outside_strings_and_restored():
    t = HEAD + 'sme_state OBJECT-TYPE SYNTAX Counter64 DESCRIPTION "keep_this" ::= { x 1 } -- a_comment\nEND\n'
    out = mark_underscores(t)
    assert f"sme{US_MARK}state OBJECT-TYPE" in out and '"keep_this"' in out and "_" not in out.replace('"keep_this"', "")
    assert unmark({"n": [f"a{US_MARK}b"]}) == {"n": ["a_b"]}


def test_capitalised_value_names_are_prefixed_everywhere_and_restored():
    t = (HEAD + "MBEntry ::= SEQUENCE { MBModelName DisplayString }\n"
         'MBModelName OBJECT-TYPE SYNTAX DisplayString DESCRIPTION "MBModelName text" ::= { x 1 }\n'
         "grp OBJECT-GROUP OBJECTS { MBModelName } ::= { x 2 }\nEND\n")
    out = mark_capitalised_values(t)
    assert out.count(UC_MARK + "MBModelName") == 3  # definition, SEQUENCE member, OBJECTS reference
    assert '"MBModelName text"' in out and "MBEntry ::=" in out  # strings and types untouched
    assert unmark(UC_MARK + "MBModelName") == "MBModelName"


def test_capitalised_enum_labels_are_prefixed():
    t = HEAD + "c OBJECT-TYPE SYNTAX Integer32{PowerOff(0), PowerOn(1)} ::= { x 1 }\nd OBJECT-TYPE SYNTAX DisplayString (SIZE (8)) ::= { x 2 }\nEND\n"
    out = mark_capitalised_values(t)
    assert f"{{{UC_MARK}PowerOff(0), {UC_MARK}PowerOn(1)}}" in out and "SIZE (8)" in out


def test_keywords_are_not_value_names_and_integer32_enums_become_integer():
    t = HEAD + "IMPORTS OBJECT-TYPE FROM SNMPv2-SMI;\nAbc OBJECT-TYPE SYNTAX Integer32{on(1)} ::= { x 1 }\nEND\n"
    out = enum_on_integer32(mark_capitalised_values(t))
    assert "IMPORTS OBJECT-TYPE" in out and f"{UC_MARK}Abc OBJECT-TYPE" in out and "SYNTAX INTEGER{on(1)}" in out


def test_enum_syntax_fixes_round_trip():
    t = (HEAD + 'a OBJECT-TYPE SYNTAX INTEGER { 100(0), 10(1), "0:00"(2), card(\'E0\'h) } ::= { x 1 }\n'
         "g OBJECT-GROUP OBJECTS { a, } ::= { x 2 }\nBitField ::= BITS\nEND\n")
    out = fix_enum_syntax(t)
    assert "card(224)" in out and "OBJECTS { a }" in out and "BitField ::= OCTET STRING" in out
    labels = re.findall(r"(zmibsitex[0-9a-f]+)\(", out)
    assert [unmark(x) for x in labels] == ["100", "10", "0:00"]


def test_shim_module_imports_are_redirected():
    from mibsite.aliases import rewrite_imports
    assert "FROM SNMPv2-SMI;" in rewrite_imports("IMPORTS Counter32 FROM SNMPv2-SMI-v1;", {"SNMPv2-SMI-v1", "SNMPv2-SMI"})


def test_lowercase_sequence_types_are_renamed_only_as_types():
    t = (HEAD + "pppoeTable OBJECT-TYPE SYNTAX SEQUENCE OF pppoeEntry ::= { x 1 }\n"
         "pppoeEntry OBJECT-TYPE SYNTAX pppoeEntry INDEX { pppoeIdx } ::= { pppoeTable 1 }\n"
         "pppoeEntry ::= SEQUENCE { pppoeIdx Integer32 }\nEND\n")
    out = mark_lowercase_types(t)
    from mibsite.lenient import LC_MARK
    assert f"SEQUENCE OF {LC_MARK}pppoeEntry" in out and f"SYNTAX {LC_MARK}pppoeEntry" in out
    assert f"{LC_MARK}pppoeEntry ::= SEQUENCE" in out
    assert "pppoeEntry OBJECT-TYPE" in out and "{ pppoeTable 1 }" in out  # the row object keeps its name
    assert unmark(f"SEQUENCE OF {LC_MARK}pppoeEntry") == "SEQUENCE OF pppoeEntry"


def test_smiv2_module_with_a_rfc1155_import_and_v1_counter():
    t = (HEAD + "IMPORTS MODULE-IDENTITY, OBJECT-TYPE FROM SNMPv2-SMI IpAddress FROM RFC1155-SMI;\n"
         "m MODULE-IDENTITY ::= { x 0 }\nc OBJECT-TYPE SYNTAX Counter ::= { x 1 }\n"
         "g OBJECT-TYPE SYNTAX Gauge32 ::= { x 2 }\nEND\n")
    out = add_missing_standard_imports(t)
    assert "SYNTAX Counter32" in out
    assert {"Counter32", "Gauge32"} <= set(parse_imports(out)["SNMPv2-SMI"])


def test_names_ending_in_hyphen():
    t = HEAD + "c OBJECT-TYPE SYNTAX INTEGER { g723High-(5), acNetCoder-9-(6), ok-name(7) } ::= { x 1 }\nEND\n"
    out = mark_underscores(t)
    assert "g723High-(5)" not in out and "ok-name(7)" in out and "::= { x 1 }" in out
    assert re.findall(r"\{ (\S+)\(5\), (\S+)\(6\)", out) and [unmark(x) for x in re.findall(r"\{ (\S+)\(5\), (\S+)\(6\)", out)[0]] == ["g723High-", "acNetCoder-9-"]


def test_smiv1_module_gets_rfc1155_imports_and_type_typos_are_fixed():
    v1 = (HEAD + "IMPORTS enterprises FROM RFC1155-SMI OBJECT-TYPE FROM RFC-1212;\n"
          "c OBJECT-TYPE SYNTAX Counter ACCESS read-only STATUS mandatory ::= { x 1 }\n"
          "g OBJECT-TYPE SYNTAX GAUGE ACCESS read-only STATUS mandatory ::= { x 2 }\nEND\n")
    out = add_missing_standard_imports(v1)
    assert set(parse_imports(out)["RFC1155-SMI"]) == {"enterprises", "Counter", "Gauge"} and "SYNTAX Gauge " in out
    v2 = (HEAD + "IMPORTS MODULE-IDENTITY, OBJECT-TYPE FROM SNMPv2-SMI;\nm MODULE-IDENTITY ::= { x 0 }\n"
          "a OBJECT-TYPE SYNTAX STRING ::= { x 1 }\nb OBJECT-TYPE SYNTAX UInteger32 ::= { x 2 }\n"
          "c OBJECT-TYPE SYNTAX OCTET STRING ::= { x 3 }\nEND\n")
    out = add_missing_standard_imports(v2)
    assert "a OBJECT-TYPE SYNTAX OCTET STRING" in out and "SYNTAX Unsigned32" in out and "OCTET OCTET" not in out
    assert "Unsigned32" in parse_imports(out)["SNMPv2-SMI"]


def test_defval_range_after_enum_empty_objects_hex_and_odd_labels():
    t = (HEAD + "a OBJECT-TYPE SYNTAX INTEGER { on(1) }(1..16) DEFVAL { FALSE } ::= { x 1 }\n"
         "b OBJECT-TYPE SYNTAX Unsigned32 ( 0 .. 0xffffffff) DEFVAL { { 1 } } ::= { x 2 }\n"
         "c OBJECT-TYPE SYNTAX INTEGER { packet/attack(3) } ::= { x 3 }\n"
         "n NOTIFICATION-TYPE OBJECTS { } ::= { x 4 }\nEND\n")
    out = fix_enum_syntax(t)
    assert "DEFVAL" not in out and "(1..16)" not in out and "OBJECTS" not in out
    assert "4294967295" in out and "::= { x 1 }" in out and "::= { x 2 }" in out
    [label] = re.findall(r"(zmibsitex[0-9a-f]+)\(3\)", out)
    assert unmark(label) == "packet/attack"


def test_split_object_identifier_is_not_a_duplicate_type():
    t = HEAD + "a OBJECT\n    IDENTIFIER ::= { x 1 }\nb OBJECT\n    IDENTIFIER ::= { x 2 }\nEND\n"
    assert rename_duplicate_definitions(t) == (t, [])


def test_lowercase_module_names():
    t = "companyMIB DEFINITIONS ::= BEGIN\nIMPORTS a FROM otherMib b FROM SNMPv2-SMI;\nEND\n"
    out = mark_module_names(t)
    assert out.startswith(LM_MARK + "companyMIB DEFINITIONS") and f"FROM {LM_MARK}otherMib" in out
    assert "FROM SNMPv2-SMI" in out and unmark(LM_MARK + "companyMIB") == "companyMIB"

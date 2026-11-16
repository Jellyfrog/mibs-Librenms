from mibsite.parse_regex import parse_with_regex

TEXT = '''BAD-MIB DEFINITIONS ::= BEGIN
IMPORTS enterprises, foo FROM SNMPv2-SMI;
badRoot OBJECT IDENTIFIER ::= { enterprises 99996 }
badThing OBJECT-TYPE
    SYNTAX Integer32 ??? garbage
    DESCRIPTION "A broken thing."
    ::= { badRoot 1 }
badFar OBJECT IDENTIFIER ::= { someImported 3 }
badNum OBJECT IDENTIFIER ::= { 1 3 6 1 4 1 99995 }
END'''


def test_regex_tier():
    m = parse_with_regex("BAD-MIB", TEXT, "acme", "acme/BAD-MIB")
    objs = {o.name: o for o in m.objects}
    assert m.tier == "regex"
    assert objs["badRoot"].oid == "1.3.6.1.4.1.99996"
    assert objs["badThing"].oid == "1.3.6.1.4.1.99996.1" and objs["badThing"].description == "A broken thing."
    assert objs["badFar"].oid is None and objs["badFar"].parent_ref == ("someImported", 3)
    assert objs["badNum"].oid == "1.3.6.1.4.1.99995"
    assert m.imports == {"SNMPv2-SMI": ["enterprises", "foo"]}


def test_regex_nothing():
    assert parse_with_regex("X", "X DEFINITIONS ::= BEGIN END", "_root", "X") is None

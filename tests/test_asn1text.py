from mibsite.asn1text import strip_comments, detect_modules, split_modules, parse_imports, defined_names


def test_strip_comments_keeps_strings():
    t = 'a -- comment\nb DESCRIPTION "x -- y" -- tail\n'
    out = strip_comments(t)
    assert "comment" not in out and "tail" not in out
    assert '"x -- y"' in out


def test_detect_modules_multiline_header():
    assert detect_modules("FOO-MIB\n   DEFINITIONS ::= BEGIN\nEND") == ["FOO-MIB"]


def test_detect_modules_ignores_commented():
    assert detect_modules("-- OLD-MIB DEFINITIONS ::= BEGIN\nNEW-MIB DEFINITIONS ::= BEGIN\nEND") == ["NEW-MIB"]


def test_split_modules(fixtures_dir):
    text = (fixtures_dir / "mibs/acme/TWO-MODULES").read_text()
    parts = split_modules(text)
    assert [p[0] for p in parts] == ["FIRST-MIB", "SECOND-MIB"]
    assert "firstRoot OBJECT IDENTIFIER" in parts[0][1]
    assert "secondNode" in parts[1][1] and "firstRoot OBJECT IDENTIFIER" not in parts[1][1]


def test_parse_imports(fixtures_dir):
    text = (fixtures_dir / "mibs/GOOD-MIB").read_text()
    imps = parse_imports(text)
    assert imps["SNMPv2-TC"] == ["TEXTUAL-CONVENTION", "DisplayString"]
    assert "enterprises" in imps["SNMPv2-SMI"]


def test_defined_names(fixtures_dir):
    names = defined_names((fixtures_dir / "mibs/GOOD-MIB").read_text())
    assert names[:3] == ["goodMIB", "goodNotifications", "goodObjects"]
    assert "goodStateChange" in names and "GoodState" not in names


def test_raw_descriptions_keep_mib_line_breaks():
    from mibsite.asn1text import raw_descriptions
    t = ("X DEFINITIONS ::= BEGIN\r\n"
         "T ::= TEXTUAL-CONVENTION\r\n    STATUS current\r\n    DESCRIPTION\r\n"
         '            "This is an extension of the\r\n            InterfaceIndex convention.\r\n\r\n'
         '            Second paragraph."\r\n    SYNTAX Integer32\r\n'
         'o OBJECT-TYPE SYNTAX T DESCRIPTION "one line" ::= { x 1 }\r\nEND\r\n')
    d = raw_descriptions(t)
    assert d["T"] == "This is an extension of the\nInterfaceIndex convention.\n\nSecond paragraph."
    assert d["o"] == "one line"

from mibsite.aliases import resolve_module, resolve_symbol_module, rewrite_imports

AVAILABLE = {"RFC1213-MIB", "RFC-1212", "RFC-1215", "FRAME-RELAY-DTE-MIB", "IF-MIB", "RFC1155-SMI"}


def test_resolve_misspelling():
    assert resolve_module("RFC-1213", AVAILABLE) == "RFC1213-MIB"
    assert resolve_module("RFC1212", AVAILABLE) == "RFC-1212"
    assert resolve_module("RFC1212-MIB", AVAILABLE) == "RFC-1212"
    assert resolve_module("RFC1215", AVAILABLE) == "RFC-1215"


def test_resolve_legacy_rename():
    assert resolve_module("RFC1315-MIB", AVAILABLE) == "FRAME-RELAY-DTE-MIB"


def test_existing_name_never_aliased():
    assert resolve_module("RFC1155-SMI", AVAILABLE) == "RFC1155-SMI"


def test_unknown_passthrough():
    assert resolve_module("NOPE-MIB", AVAILABLE) == "NOPE-MIB"


def test_symbol_prefix_rules():
    assert resolve_symbol_module("RFC1213-MIB", "ifIndex") == "IF-MIB"
    assert resolve_symbol_module("RFC1213-MIB", "mib-2") == "SNMPv2-SMI"
    assert resolve_symbol_module("RFC1213-MIB", "mib-2x") is None
    assert resolve_symbol_module("IF-MIB", "ifIndex") is None


def test_rewrite_imports():
    text = "IMPORTS a FROM RFC-1213 b FROM RFC1155-SMI c FROM NOPE-MIB;"
    assert rewrite_imports(text, AVAILABLE) == "IMPORTS a FROM RFC1213-MIB b FROM RFC1155-SMI c FROM NOPE-MIB;"

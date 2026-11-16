"""Module-name aliases, ported from net-snmp snmplib/parse.c `module_map[]`."""
from __future__ import annotations

import re

# (old, new, tag, tag_len) exactly as net-snmp; tag None = whole module.
SYMBOL_ALIASES: list[tuple[str, str, str | None, int]] = [
    ("RFC1065-SMI", "RFC1155-SMI", None, 0),
    ("RFC1066-MIB", "RFC1156-MIB", None, 0),
    ("RFC1156-MIB", "RFC1158-MIB", None, 0),
    ("RFC1158-MIB", "RFC1213-MIB", None, 0),
    ("RFC1155-SMI", "SNMPv2-SMI", None, 0),
    ("RFC1213-MIB", "SNMPv2-SMI", "mib-2", 0),
    ("RFC1213-MIB", "SNMPv2-MIB", "sys", 3),
    ("RFC1213-MIB", "IF-MIB", "if", 2),
    ("RFC1213-MIB", "IP-MIB", "ip", 2),
    ("RFC1213-MIB", "IP-MIB", "icmp", 4),
    ("RFC1213-MIB", "TCP-MIB", "tcp", 3),
    ("RFC1213-MIB", "UDP-MIB", "udp", 3),
    ("RFC1213-MIB", "SNMPv2-SMI", "transmission", 0),
    ("RFC1213-MIB", "SNMPv2-MIB", "snmp", 4),
    ("RFC1231-MIB", "TOKENRING-MIB", None, 0),
    ("RFC1271-MIB", "RMON-MIB", None, 0),
    ("RFC1286-MIB", "SOURCE-ROUTING-MIB", "dot1dSr", 7),
    ("RFC1286-MIB", "BRIDGE-MIB", None, 0),
    ("RFC1315-MIB", "FRAME-RELAY-DTE-MIB", None, 0),
    ("RFC1316-MIB", "CHARACTER-MIB", None, 0),
    ("RFC1406-MIB", "DS1-MIB", None, 0),
    ("RFC-1213", "RFC1213-MIB", None, 0),
]

MODULE_ALIASES: dict[str, str] = {old: new for old, new, tag, _ in SYMBOL_ALIASES if tag is None}
# Extensions (not in net-snmp): misspellings seen in LibreNMS MIBs.
MODULE_ALIASES.update({"RFC1212": "RFC-1212", "RFC1212-MIB": "RFC-1212", "RFC1215": "RFC-1215"})

_FROM_RE = re.compile(r"(\bFROM\s+)([A-Za-z][A-Za-z0-9_-]*)")


def resolve_module(name: str, available: set[str]) -> str:
    seen: set[str] = set()
    while name not in available and name in MODULE_ALIASES and name not in seen:
        seen.add(name)
        name = MODULE_ALIASES[name]
    return name


def resolve_symbol_module(module: str, symbol: str) -> str | None:
    for old, new, tag, tag_len in SYMBOL_ALIASES:
        if old != module or tag is None:
            continue
        if (tag_len == 0 and symbol == tag) or (tag_len and symbol[:tag_len] == tag[:tag_len]):
            return new
    return None


# Shim modules redirected even though the file exists: SNMPv2-SMI-v1 re-declares SNMPv2 types on top of
# SMIv1 ones (Counter32 ::= Counter), which pysmi cannot build; importers only want the standard names.
FORCED_ALIASES = {"SNMPv2-SMI-v1": "SNMPv2-SMI"}


def rewrite_imports(text: str, available: set[str]) -> str:
    return _FROM_RE.sub(
        lambda m: m.group(1) + FORCED_ALIASES.get(m.group(2), resolve_module(m.group(2), available)), text)

"""Tier 3: tolerant regex scrape of `name MACRO ... ::= { parent n }` assignments."""
from __future__ import annotations

import re

from .asn1text import parse_imports, strip_comments
from .model import Module, Obj

WELL_KNOWN = {
    "ccitt": "0", "iso": "1", "joint-iso-ccitt": "2", "org": "1.3", "dod": "1.3.6", "internet": "1.3.6.1",
    "directory": "1.3.6.1.1", "mgmt": "1.3.6.1.2", "mib-2": "1.3.6.1.2.1", "transmission": "1.3.6.1.2.1.10",
    "experimental": "1.3.6.1.3", "private": "1.3.6.1.4", "enterprises": "1.3.6.1.4.1",
    "security": "1.3.6.1.5", "snmpV2": "1.3.6.1.6", "zeroDotZero": "0.0",
}
_ASSIGN = re.compile(
    r"^[ \t]*([a-z][\w-]*)\s+"
    r"(OBJECT-TYPE|OBJECT\s+IDENTIFIER|NOTIFICATION-TYPE|MODULE-IDENTITY|OBJECT-IDENTITY|TRAP-TYPE|"
    r"OBJECT-GROUP|NOTIFICATION-GROUP|MODULE-COMPLIANCE|AGENT-CAPABILITIES)\b"
    r"(.*?)::=\s*\{\s*([^}]*?)\s*\}",
    re.M | re.S,
)
_KIND = {"OBJECT-TYPE": "scalar", "NOTIFICATION-TYPE": "notification", "TRAP-TYPE": "notification",
         "MODULE-IDENTITY": "identity", "OBJECT-GROUP": "group", "NOTIFICATION-GROUP": "group",
         "MODULE-COMPLIANCE": "compliance"}


def parse_with_regex(name: str, text: str, dir: str, file: str) -> Module | None:
    clean = strip_comments(text)
    objs: list[Obj] = []
    for m in _ASSIGN.finditer(clean):
        oname, macro, body, value = m.group(1), re.sub(r"\s+", " ", m.group(2)), m.group(3), m.group(4).split()
        desc = re.search(r'DESCRIPTION\s+"(.*?)"', body, re.S)
        obj = Obj(oname, None, _KIND.get(macro, "node"),
                  description=re.sub(r"[ \t]*\n[ \t]*", "\n", desc.group(1)).strip() if desc else None)
        if value and all(v.isdigit() for v in value):
            obj.oid = ".".join(value)
        elif len(value) >= 2 and value[-1].isdigit():
            obj.parent_ref = (value[-2].split("(")[0], int(value[-1]))
        else:
            continue
        objs.append(obj)
    if not objs:
        return None
    local = dict(WELL_KNOWN)
    changed = True
    while changed:
        changed = False
        for o in objs:
            if o.oid is None and o.parent_ref and o.parent_ref[0] in local:
                o.oid = f"{local[o.parent_ref[0]]}.{o.parent_ref[1]}"
                o.parent_ref = None
                changed = True
            if o.oid and local.get(o.name) != o.oid:
                local[o.name] = o.oid
    return Module(name=name, dir=dir, file=file, tier="regex", imports=parse_imports(text), objects=objs)

"""Which MIBs and objects LibreNMS itself uses, found in its PHP code and YAML OS definitions as:
- `MODULE::object`, also in YAML lists and `{{ MODULE::object }}` templates
- the MIB name on its own (`snmpwalk_cache_oid($device, 'cpwVcID', [], 'CISCO-IETF-PW-MPLS-MIB')`,
  `->mibs(['ENTITY-MIB'])`, `A-MIB:B-MIB`); quoted object names of that MIB in the same file count as its objects
- numeric OIDs (`num_oid: '.1.3.6.1.4.1.318.1.1.1.2.2.1.{{ $index }}'`)
- an object name on its own (`oid: upsBatteryTemp`, `{{ ifName }}`, `snmp_get($device, 'sysUpTime.0')`): only
  camelCase names in object positions that belong to a single MIB (in the whole tree, or among the MIBs in the
  OS's mib_dir), so plain words do not count
A MIB never counts just because it sits in a folder the code names (`mib_dir: adva` in the OS's os_detection YAML,
`->mibDir('alaxala')` in PHP): the folder only picks which copy of a MIB that several folders ship gets the credit
for a reference found in one of the ways above, and narrows down bare object names."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .discover import ROOT_DIR
from .model import Module

# what the build fetches (scripts/fetch-librenms.sh): OS definitions and the PHP code that polls devices
SOURCE_DIRS = ("resources/definitions", "LibreNMS", "includes", "app")
_REF_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9-]*)::([a-zA-Z][A-Za-z0-9-]*)")
_NAME_RE = re.compile(r"(?<![\w-])([A-Za-z][\w-]*[A-Za-z0-9])(?![\w-])")
_OID_RE = re.compile(r"(?<![\w.])\.?(1\.3\.6\.1(?:\.\d+)+)")
# objects that hold or describe data; plain nodes and module identities sit above whole vendor subtrees
_DATA_KINDS = {"scalar", "column", "table", "row", "notification"}
_MIB_DIR_RE = re.compile(r"^mib_dir:\s*['\"]?([\w./-]+)", re.M)
_PHP_MIB_DIR_RE = re.compile(r"mibDir\(\s*['\"]([\w./-]+)['\"]")
_QUOTED_RE = re.compile(r"['\"]([a-zA-Z][A-Za-z0-9-]*)['\"]")


# object positions for bare names: quoted strings (PHP arguments, YAML), YAML oid/value/index/data values and
# {{ templates }}; an instance suffix (.0, .{{ $index }}) is cut off
_BARE_RE = re.compile(r"['\"]([a-z][A-Za-z0-9-]*)(?:\.[^'\"]*)?['\"]"
                      r"|^[ \t-]*(?:oid|value|index|data):[ \t]*([a-z][A-Za-z0-9-]*)[ \t]*(?:\.\S*)?$"
                      r"|^[ \t]*-[ \t]+([a-z][A-Za-z0-9-]*)[ \t]*$"
                      r"|\{\{[ \t]*([a-z][A-Za-z0-9-]*)[ \t]*\}\}", re.M)
_CAMEL_RE = re.compile(r"[a-z][a-z0-9]*[A-Z]")


@dataclass
class Usage:
    objects: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))  # module id -> object names
    by_ref: set[str] = field(default_factory=set)    # module ids seen as MODULE::object
    by_name: set[str] = field(default_factory=set)   # module ids seen by name alone
    by_oid: set[str] = field(default_factory=set)    # module ids seen through a numeric OID
    by_object: set[str] = field(default_factory=set)  # module ids seen through a bare object name

    @property
    def modules(self) -> set[str]:
        return self.by_ref | self.by_name | self.by_oid | self.by_object


def _pick(mods, dirs: set[str]):
    """One copy of a MIB that several folders ship: the one in a folder the code names, the top-level one, else
    the first by path. `mods` holds Modules or (Module, object) pairs."""
    mod = (lambda x: x[0]) if mods and isinstance(mods[0], tuple) else (lambda x: x)
    return min(mods, key=lambda x: (mod(x).dir not in dirs, mod(x).dir != ROOT_DIR, mod(x).id))


def _os_mib_dirs(librenms: Path) -> dict[str, set[str]]:
    """OS name -> its mib_dir, from resources/definitions/os_detection/<os>.yaml"""
    out = {}
    for p in (librenms / "resources/definitions/os_detection").glob("*.yaml"):
        out[p.stem] = set(_MIB_DIR_RE.findall(p.read_text(errors="replace")))
    return out


def collect_usage(librenms: Path, modules: list[Module]) -> Usage:
    by_name: dict[str, list[Module]] = defaultdict(list)
    for m in modules:
        by_name[m.name].append(m)
    objects = {m.id: {o.name for o in m.objects} for m in modules}
    by_oid: dict[str, list[tuple[Module, str]]] = defaultdict(list)
    for m in modules:
        for o in m.objects:
            if o.kind in _DATA_KINDS and o.oid:
                by_oid[o.oid].append((m, o.name))
    owners_of: dict[str, list[Module]] = defaultdict(list)  # object name -> MIBs defining it
    for m in modules:
        for o in m.objects:
            if o.kind in _DATA_KINDS:
                owners_of[o.name].append(m)
    os_dirs = _os_mib_dirs(librenms)
    usage = Usage()

    def credit(mid: str, obj: str | None, kind: set[str]) -> None:
        kind.add(mid)
        if obj:
            usage.objects[mid].add(obj)

    for d in SOURCE_DIRS:
        root = librenms / d
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.suffix not in (".php", ".yaml", ".yml") or not p.is_file():
                continue
            text = p.read_text(errors="replace")
            dirs = set(_PHP_MIB_DIR_RE.findall(text)) | os_dirs.get(p.stem, set()) | set(_MIB_DIR_RE.findall(text))
            for mod, sym in _REF_RE.findall(text):
                # PHP static calls (Str::of) match too: the left side is no MIB, or the right side not its object
                owners = [m for m in by_name.get(mod, ()) if sym in objects[m.id]]
                if owners:
                    credit(_pick(owners, dirs).id, sym, usage.by_ref)
            named = []
            for name in set(_NAME_RE.findall(text)):
                # names without "-" are often plain words (LAN, SWITCH, DEVICE); those count only in the other forms
                if "-" in name and name in by_name:
                    named.append(_pick(by_name[name], dirs))
            quoted = set(_QUOTED_RE.findall(text))
            for m in named:
                credit(m.id, None, usage.by_name)
                for obj in quoted & objects[m.id]:
                    usage.objects[m.id].add(obj)
            for groups in _BARE_RE.findall(text):
                name = next(g for g in groups if g)
                if not _CAMEL_RE.match(name) or name not in owners_of:
                    continue
                owners = owners_of[name]
                if len({m.name for m in owners}) > 1:  # several MIBs define it: only if the OS's folder settles it
                    owners = [m for m in owners if m.dir in dirs]
                if owners and len({m.name for m in owners}) == 1:
                    credit(_pick(owners, dirs).id, name, usage.by_object)
            for oid in set(_OID_RE.findall(text)):
                arcs = oid.split(".")
                while len(arcs) > 6:  # longest data object at or above the OID (instances like .0 or .ifIndex)
                    hits = by_oid.get(".".join(arcs))
                    if hits:
                        m, obj = _pick(hits, dirs)
                        credit(m.id, obj, usage.by_oid)
                        break
                    arcs.pop()
    usage.objects = dict(usage.objects)
    return usage

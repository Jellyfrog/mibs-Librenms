"""Tier 1: full parse with pysmi's JSON code generator."""
from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from pysmi.codegen import JsonCodeGen
from pysmi.compiler import MibCompiler
from pysmi.parser import SmiStarParser
from pysmi.reader import FileReader
from pysmi.searcher import StubSearcher
from pysmi.writer import CallbackWriter

from .aliases import rewrite_imports
from .lenient import (DUP_RE, add_missing_standard_imports, enum_on_integer32, fix_enum_syntax,
                      mark_capitalised_values, mark_lowercase_types, mark_module_names, mark_name,
                      mark_underscores,
                      rename_duplicate_definitions, unmark)
from .model import Module, Obj, TextualConvention


# Modules pysmi treats as built in: asked to compile one, it answers "untouched". net-snmp parses them.
BASE_MIBS = frozenset(JsonCodeGen.baseMibs)


# Per-process caches. A worker compiles many MIBs, and each compile re-reads and re-parses every MIB in its
# import chain (HUAWEI-MIB is imported by ~360 others), which was most of the parse time. The prepared
# text depends only on the file and the build's module set, and a parse tree only on that text.
_TEXT_CACHE: dict[tuple[str, str], tuple] = {}
_TREE_CACHE: dict[int, list] = {}
REUSE = True  # set False to compare against uncached compiles
CACHE_LIMIT = 1000


class CachingParser:
    """SmiStarParser whose results are reused for identical text."""

    def __init__(self):
        self._parser = SmiStarParser()

    def parse(self, data, **kwargs):
        if not REUSE:
            return self._parser.parse(data, **kwargs)
        key = hash(data)
        if key not in _TREE_CACHE:
            if len(_TREE_CACHE) >= CACHE_LIMIT:  # bound memory: ~1000 trees is roughly 200 MB
                _TREE_CACHE.clear()
                _TEXT_CACHE.clear()
            _TREE_CACHE[key] = list(self._parser.parse(data, **kwargs))
        return _TREE_CACHE[key]


# pysmi's own limit is 10 MB; 20 MB lets alaxala/AX-SMC-MIB (12 MB, ~20 s) through but keeps
# metaswitch/METASWITCH-MIB (46 MB, ~12 min and 1.2 GB) on net-snmp
MAX_MIB_BYTES = 20_000_000


class AliasFileReader(FileReader):
    """FileReader (non-recursive) that rewrites aliased `FROM` module names in every file it serves."""
    maxMibSize = MAX_MIB_BYTES

    def __init__(self, path: Path, available: set[str], notes: dict[str, list[str]]):
        super().__init__(str(path), recursive=False)
        self._path_str = str(path)
        self._available = available
        self._notes = notes  # mib name -> lenient fixes applied, shared by all readers of one compile

    def get_data(self, mibname, **options):
        key = (self._path_str, mibname)
        if REUSE and key in _TEXT_CACHE:
            info, data, notes = _TEXT_CACHE[key]
            if notes:
                self._notes[mibname] = notes
            return info, data
        # pysmi asks for module names as they appear after mark_underscores (AH_TRAP_MIB is requested as
        # AHXmibsiteusTRAPXmibsiteusMIB); the file on disk has the real name
        info, data = super().get_data(unmark(mibname), **options)
        info.name = mibname
        data = add_missing_standard_imports(rewrite_imports(data, self._available))
        data = mark_lowercase_types(mark_capitalised_values(mark_underscores(fix_enum_syntax(data))))
        data = mark_module_names(data)
        data = enum_on_integer32(data)
        data, renamed = rename_duplicate_definitions(data)
        notes = [f"defined more than once: {', '.join(unmark(renamed))}"] if renamed else []
        if notes:
            self._notes[mibname] = notes
        if REUSE:
            _TEXT_CACHE[key] = (info, data, notes)
        return info, data


def compile_pysmi(module_name: str, dirs: list[Path], available: set[str]) -> tuple[dict | None, list[str]]:
    """Return (json or None, messages). Messages list missing dependencies even on success."""
    out: dict[str, str] = {}
    compiler = MibCompiler(
        CachingParser(), JsonCodeGen(), CallbackWriter(lambda name, data, ctx: out.__setitem__(name, data))
    )
    notes: dict[str, list[str]] = {}
    compiler.add_sources(*(AliasFileReader(d, available, notes) for d in dirs))
    compiler.add_searchers(StubSearcher(*JsonCodeGen.baseMibs))
    wanted = mark_name(module_name)  # SMI module names can't contain "_"; see mark_underscores
    try:
        statuses = compiler.compile(wanted, ignoreErrors=True, rebuild=True, genTexts=True)
    except Exception as e:  # pysmi can raise on odd input; never let it escape
        return None, [f"pysmi crashed: {e!r}"]
    messages = notes.get(wanted, []) + [f"missing dependency: {unmark(k)}" for k, v in statuses.items() if str(v) == "missing"]
    status = statuses.get(wanted)
    if str(status) == "compiled" and wanted in out:
        return json.loads(out[wanted]), messages
    return None, [f"pysmi {status}: {getattr(status, 'error', '')}".strip(), *messages]


def _ranges(items: list[dict]) -> str:
    return " | ".join(f"{r['min']}" if r["min"] == r["max"] else f"{r['min']}..{r['max']}" for r in items)


def format_syntax(syntax: dict | None) -> tuple[str | None, dict[str, int] | None]:
    if not syntax:
        return None, None
    c = syntax.get("constraints") or {}
    text = syntax.get("type") or ""
    if c.get("range"):
        text += f" ({_ranges(c['range'])})"
    if c.get("size"):
        text += f" (SIZE ({_ranges(c['size'])}))"
    enums = c.get("enumeration") or syntax.get("bits")
    return (text or None), (dict(enums) if enums else None)


def _refs(v: dict, key: str) -> list[str]:
    return [x["object"] for x in v.get(key, []) if isinstance(x, dict) and "object" in x]


def normalize_pysmi(js: dict, name: str, dir: str, file: str) -> Module:
    mod = Module(name=name, dir=dir, file=file, tier="pysmi")
    for v in js.values():
        if not isinstance(v, dict):
            continue
        cls = v.get("class")
        if cls == "imports":
            mod.imports = {k: list(s) for k, s in v.items() if k != "class"}
        elif cls == "moduleidentity":
            mod.identity = {
                "organization": v.get("organization"),
                "contact": v.get("contactinfo"),
                "description": v.get("description"),
                "last_updated": v.get("lastupdated"),
                "revisions": [{"date": r.get("revision"), "description": r.get("description")}
                              for r in v.get("revisions", [])],
            }
            mod.objects.append(Obj(v["name"], v.get("oid"), "identity", description=v.get("description")))
        elif cls == "textualconvention":
            syn, enums = format_syntax(v.get("type"))
            mod.tcs.append(TextualConvention(v["name"], syn, v.get("displayhint"), v.get("status"),
                                             v.get("description"), enums))
        elif cls == "objecttype":
            syn, enums = format_syntax(v.get("syntax"))
            mod.objects.append(Obj(
                v["name"], v.get("oid"), v.get("nodetype") or "scalar", syn, v.get("maxaccess"), v.get("status"),
                v.get("units"), v.get("description"), _refs(v, "indices"),
                (v.get("augmention") or {}).get("object"), enums,
            ))
        elif cls in ("notificationtype", "trap"):
            mod.objects.append(Obj(v["name"], v.get("oid"), "notification", status=v.get("status"),
                                   description=v.get("description"), objects=_refs(v, "objects")))
        elif cls in ("objectgroup", "notificationgroup"):
            mod.objects.append(Obj(v["name"], v.get("oid"), "group", status=v.get("status"),
                                   description=v.get("description"), objects=_refs(v, "objects")))
        elif cls == "modulecompliance":
            mod.objects.append(Obj(v["name"], v.get("oid"), "compliance", status=v.get("status"),
                                   description=v.get("description"), objects=_refs(v, "modulecompliance")))
        elif "oid" in v and "name" in v:
            mod.objects.append(Obj(v["name"], v["oid"], "node", status=v.get("status"),
                                   description=v.get("description")))
    # undo lenient's renames (underscores, capitalised values) everywhere a name can appear
    for x in [*mod.objects, *mod.tcs]:
        for f in fields(x):
            setattr(x, f.name, unmark(getattr(x, f.name)))
    mod.imports = unmark(mod.imports)
    # names renamed by lenient.rename_duplicate_definitions: show every definition under its real name
    dup = {DUP_RE.sub("", x.name) for x in [*mod.objects, *mod.tcs] if DUP_RE.search(x.name)}
    for x in [*mod.objects, *mod.tcs]:
        x.name = DUP_RE.sub("", x.name)
    for o in mod.objects:
        o.defined_twice = o.name in dup
    return mod

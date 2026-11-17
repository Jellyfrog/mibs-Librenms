"""Fixes for common vendor-MIB mistakes that net-snmp tolerates but pysmi rejects, applied to the text
pysmi reads (never to the files on disk):

- add_missing_standard_imports: e.g. Counter64 or DisplayString used without importing them
  ("Unknown parents for symbols ..."). In SMIv2 modules SMIv1 `Counter`/`Gauge` become Counter32/Gauge32.
- rename_duplicate_definitions: a name assigned twice (HUAWEI-MIB defines USG6635F as { fw 284 } and
  { fw 402 }); pysmi rejects the whole module, and with it every MIB importing it. Later definitions get a
  temporary unique name; the site shows all of them under the real name, marked "defined twice".
- mark_underscores: names like sme_ca_cur_health_state (SMI allows only letters, digits and hyphens);
  net-snmp rejects them too. "_" becomes a temporary marker; the site shows the original name.
- mark_lowercase_types: table entry types named in lowercase (fooEntry ::= SEQUENCE {…}, used as
  SEQUENCE OF fooEntry); type names must start with a capital. Renamed in type positions only.
- enum_on_integer32: named numbers on Integer32/Unsigned32 ({up(1)}), only allowed on INTEGER.
- fix_enum_syntax: enum labels that aren't names (100(0), "0:00"(0)) are encoded, hex values ('E0'h)
  become decimal, a trailing comma before "}" goes, and a bare `BITS` type becomes OCTET STRING. Also
  DEFVAL clauses go (never shown), as do a range after an enum (INTEGER {…}(1..16)) and an empty
  OBJECTS { }; C-style hex numbers (0xffffffff) become decimal.
- mark_capitalised_values: objects named like MBModelName (value names must start lowercase). They get a
  temporary lowercase prefix; the site shows the original name.
"""
from __future__ import annotations

import re

from .asn1text import _IMPORTS_RE, defined_names, detect_modules, parse_imports, strip_comments

STANDARD: dict[str, tuple[str, ...]] = {
    "SNMPv2-SMI": ("MODULE-IDENTITY", "OBJECT-IDENTITY", "OBJECT-TYPE", "NOTIFICATION-TYPE", "Counter32",
                   "Counter64", "Gauge32", "Integer32", "Unsigned32", "IpAddress", "TimeTicks", "Opaque",
                   "enterprises", "mib-2", "internet", "experimental", "private", "zeroDotZero"),
    "SNMPv2-TC": ("TEXTUAL-CONVENTION", "DisplayString", "PhysAddress", "MacAddress", "TruthValue",
                  "TestAndIncr", "AutonomousType", "InstancePointer", "VariablePointer", "RowPointer",
                  "RowStatus", "TimeStamp", "TimeInterval", "DateAndTime", "StorageType", "TDomain", "TAddress"),
    "SNMPv2-CONF": ("MODULE-COMPLIANCE", "OBJECT-GROUP", "NOTIFICATION-GROUP", "AGENT-CAPABILITIES"),
}
# The same for SMIv1 modules (no MODULE-IDENTITY): what RFC 1155/1212/1213/1215 provide.
STANDARD_V1: dict[str, tuple[str, ...]] = {
    "RFC1155-SMI": ("Counter", "Gauge", "TimeTicks", "IpAddress", "Opaque", "NetworkAddress", "enterprises",
                    "internet", "private", "experimental", "mgmt"),
    "RFC-1212": ("OBJECT-TYPE",),
    "RFC1213-MIB": ("DisplayString", "PhysAddress", "mib-2"),
    "RFC-1215": ("TRAP-TYPE",),
}
# Misspelled or non-SMI base types seen in vendor MIBs -> (SMIv2 name, SMIv1 name). SMIv1 Counter/Gauge in an
# SMIv2 module are the same mistake the other way round.
_TYPE_FIXES = {"GAUGE": ("Gauge32", "Gauge"), "UInteger32": ("Unsigned32", "INTEGER"),
               "Hex-STRING": ("OCTET STRING", "OCTET STRING"), "STRING": ("OCTET STRING", "OCTET STRING"),
               "Counter": ("Counter32", "Counter"), "Gauge": ("Gauge32", "Gauge")}
_TYPE_FIX_RE = re.compile(r"(?<![\w-])(?<!OCTET )(?<!OCTET\t)(GAUGE|UInteger32|Hex-STRING|STRING|Counter|Gauge)(?![\w-])")
_STRING_RE = re.compile(r'"[^"]*"')
_TYPE_DEF_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9-]*)\s*::=", re.M)


def _uses(body: str, name: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", body) is not None


def add_missing_standard_imports(text: str) -> str:
    """Return `text` with misspelled base types fixed and missing standard imports added (SMIv2 or SMIv1
    set, by the module's own style), comment-stripped; or unchanged when there is nothing to do."""
    if len(detect_modules(text)) != 1:
        return text
    clean = strip_comments(text)
    if re.search(r"\bMACRO\b", clean):  # the SMI base modules themselves
        return text
    imports = parse_imports(clean)
    v2 = bool(set(STANDARD) & set(imports)) or _uses(clean, "MODULE-IDENTITY")
    table = STANDARD if v2 else STANDARD_V1
    if not v2 and not _uses(clean, "OBJECT-TYPE") and not _TYPE_DEF_RE.search(clean):
        return text  # SMIv1 modules with neither objects nor types (Counter32 ::= Counter) need nothing
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', clean)
    fixes = [m for m in _TYPE_FIX_RE.finditer(blanked) if v2 or m.group(1) not in ("Counter", "Gauge")]
    if fixes:
        out, last = [], 0
        for f in fixes:
            out += [clean[last:f.start(1)], _TYPE_FIXES[f.group(1)][0 if v2 else 1]]
            last = f.end(1)
        clean = "".join(out) + clean[last:]
        imports = parse_imports(clean)
    m = _IMPORTS_RE.search(clean)
    body = _STRING_RE.sub('""', clean[m.end():] if m else clean)  # usage outside IMPORTS and strings
    have = ({s for syms in imports.values() for s in syms} | set(defined_names(clean))
            | set(_TYPE_DEF_RE.findall(clean)))  # local types/TCs (Name ::= ...) shadow the standard ones
    missing = {mod: [s for s in syms if s not in have and _uses(body, s)] for mod, syms in table.items()}
    missing = {mod: syms for mod, syms in missing.items() if syms}
    if not missing:
        return clean if fixes else text
    if m is None:  # no IMPORTS clause at all
        clause = "\nIMPORTS " + " ".join(f"{', '.join(s)} FROM {mod}" for mod, s in missing.items()) + ";\n"
        begin = re.search(r"\bBEGIN\b", clean)
        return clean[:begin.end()] + clause + clean[begin.end():]
    section = m.group(1)
    for mod, syms in missing.items():
        frm = re.search(rf"\bFROM\s+{re.escape(mod)}(?![\w-])", section)
        if frm:  # extend that module's symbol list
            section = section[:frm.start()] + f", {', '.join(syms)} " + section[frm.start():]
        else:
            section = section.rstrip() + f"\n    {', '.join(syms)} FROM {mod}"
    return clean[:m.start(1)] + section + clean[m.end(1):]


# Start of a top-level assignment: `name MACRO ...` for the SMI macros, or `Name ::= ...` for a type.
_ASSIGN_RE = re.compile(
    r"^[ \t]*(?!(?:SYNTAX|WRITE-SYNTAX|IDENTIFIER)\b)([A-Za-z][A-Za-z0-9_-]*)[ \t]+(?:OBJECT\s+IDENTIFIER\s*::=|(?:OBJECT-TYPE|OBJECT-IDENTITY"
    r"|NOTIFICATION-TYPE|TRAP-TYPE|OBJECT-GROUP|NOTIFICATION-GROUP|MODULE-COMPLIANCE|MODULE-IDENTITY"
    r"|AGENT-CAPABILITIES|TEXTUAL-CONVENTION)\b)|^[ \t]*(?!IDENTIFIER\b)([A-Z][A-Za-z0-9_-]*)[ \t]*::=", re.M)


DUP_MARK = "-mibsiteDup"  # suffix given to a re-defined name; normalize_pysmi maps it back
DUP_RE = re.compile(re.escape(DUP_MARK) + r"\d+$")


def rename_duplicate_definitions(text: str) -> tuple[str, list[str]]:
    """Give each later definition of an already defined name a unique temporary name (NAME-mibsiteDup2, …)
    so pysmi accepts the module; the pages show it under its real name again. Returns (text, names)."""
    if len(detect_modules(text)) != 1:
        return text, []
    clean = strip_comments(text)
    # find assignment starts on a copy with string contents blanked (same length), so DESCRIPTION text
    # that happens to look like a definition is never touched
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', clean)
    if re.search(r"\bMACRO\b", blanked):  # SMI base modules: macro bodies repeat helper names by design
        return text, []
    seen: dict[str, int] = {}
    edits, renamed = [], []
    for m in _ASSIGN_RE.finditer(blanked):
        group = 1 if m.group(1) else 2
        name = m.group(group)
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            edits.append((m.end(group), f"{DUP_MARK}{seen[name]}"))
            if name not in renamed:
                renamed.append(name)
    if not edits:
        return text, []
    out, last = [], 0
    for pos, suffix in edits:
        out += [clean[last:pos], suffix]
        last = pos
    out.append(clean[last:])
    return "".join(out), renamed


US_MARK = "Xmibsiteus"  # stands for "_" inside names while pysmi parses; letters only, so always valid SMI
HY_MARK = "Xmibsitehy"  # stands for a trailing "-" (g723High-), which SMI names may not end with
_US_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*_[A-Za-z0-9_-]*")
_HY_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*-(?![A-Za-z0-9_-])")


LM_MARK = "Mmibsitelm"  # prefix for module names starting lowercase (companyMIB); module names need a capital


def mark_name(name: str) -> str:
    """A module name as pysmi sees it after mark_underscores and mark_module_names."""
    name = name.replace("_", US_MARK)
    return LM_MARK + name if name[:1].islower() else name


_LOWER_MODULE_RE = re.compile(r"(^[ \t]*|\bFROM\s+)([a-z][A-Za-z0-9_-]*)(?=\s+DEFINITIONS\b|[\s;,])", re.M)


def mark_module_names(text: str) -> str:
    """Prefix module names that start lowercase, in the module header and in FROM clauses."""
    clean = strip_comments(text)
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', clean)
    hits = [m for m in _LOWER_MODULE_RE.finditer(blanked)
            if m.group(1).strip() == "FROM" or re.match(r"\s+DEFINITIONS\b", blanked[m.end(2):])]
    if not hits:
        return text
    out, last = [], 0
    for m in hits:
        out += [clean[last:m.start(2)], LM_MARK]
        last = m.start(2)
    return "".join(out) + clean[last:]


def mark_underscores(text: str) -> str:
    """Replace "_" in identifiers, and a trailing "-", with letters-only markers (outside strings and comments)."""
    clean = strip_comments(text)
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', clean)
    tokens = {m.start(): m for m in _US_TOKEN_RE.finditer(blanked) if not m.group().endswith("_")}
    tokens.update((m.start(), m) for m in _HY_TOKEN_RE.finditer(blanked) if m.start() not in tokens)
    if not tokens:
        return text
    out, last = [], 0
    for _, m in sorted(tokens.items()):
        word = m.group().replace("_", US_MARK)
        if word.endswith("-"):
            word = word[:-1] + HY_MARK
        out += [clean[last:m.start()], word]
        last = m.end()
    out.append(clean[last:])
    return "".join(out)


UC_MARK = "zmibsiteuc"  # prefix that makes a capitalised value name start lowercase while pysmi parses
_VALUE_MACROS = ("OBJECT-TYPE", "OBJECT-IDENTITY", "NOTIFICATION-TYPE", "TRAP-TYPE", "OBJECT-GROUP",
                 "NOTIFICATION-GROUP", "MODULE-COMPLIANCE", "MODULE-IDENTITY", "AGENT-CAPABILITIES")
_CAP_VALUE_RE = re.compile(
    r"^[ \t]*(?!(?:SYNTAX|WRITE-SYNTAX|IDENTIFIER)\b)([A-Z][A-Za-z0-9_-]*)[ \t]+(?:OBJECT\s+IDENTIFIER\s*::=|(?:"
    + "|".join(_VALUE_MACROS) + r")\b)", re.M)


_KEYWORDS = {"IMPORTS", "EXPORTS", "FROM", "BEGIN", "END", "DEFINITIONS", "SYNTAX", "OBJECTS", "INDEX", "MACRO"}
_CAP_ENUM_RE = re.compile(r"(?<=[{,])\s*([A-Z][A-Za-z0-9_-]*)(?=\s*\(\s*-?\d+\s*\))")


def mark_capitalised_values(text: str) -> str:
    """Prefix with UC_MARK, outside strings and comments, so pysmi accepts them: value names this module
    defines with a capital (MBModelName, at every occurrence) and capitalised enum labels (PowerOff(0))."""
    clean = strip_comments(text)
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', clean)
    if re.search(r"\bMACRO\b", blanked):  # SMI base modules
        return text
    names = {m.group(1) for m in _CAP_VALUE_RE.finditer(blanked)} - _KEYWORDS
    hits = list(_CAP_ENUM_RE.finditer(blanked))  # enum labels like {PowerOff(0), PowerOn(1)}
    if names:
        word = re.compile(r"(?<![A-Za-z0-9_-])(" + "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
                          + r")(?![A-Za-z0-9_-])")
        hits += word.finditer(blanked)
    if not hits:
        return text
    hits.sort(key=lambda m: m.start(1))
    out, last = [], 0
    for m in hits:
        out += [clean[last:m.start(1)], UC_MARK + m.group(1)]
        last = m.end(1)
    out.append(clean[last:])
    return "".join(out)


LABEL_MARK = "zmibsitex"  # an enum label that isn't a name, hex-encoded: 100 -> zmibsitex313030
_LABEL_RE = re.compile(LABEL_MARK + r"([0-9a-f]+)")
_BAD_LABEL_RE = re.compile(r"(?<=[{,])(\s*)(\"[^\"\n]*\"|\d[\w.:-]*|[A-Za-z][\w-]*[/.+:&][^\s(),{}]*)(?=\s*\(\s*(?:-?\d+|'[0-9A-Fa-f]+'[hH])\s*\))")
_HEX_VALUE_RE = re.compile(r"(?<=\()\s*'([0-9A-Fa-f]+)'[hH]\s*(?=\))")
_TRAILING_COMMA_RE = re.compile(r",(?=\s*\})")
_BARE_BITS_RE = re.compile(r"::=(\s*)BITS\b(?!\s*\{)")
_DEFVAL_RE = re.compile(r"\bDEFVAL\s*\{")  # default values are never shown; vendors write them in many invalid ways
_RANGE_AFTER_ENUM_RE = re.compile(r"\}\s*(\(\s*-?\w+\s*\.\.\s*-?\w+\s*\))")  # INTEGER {…}(1..16)
_EMPTY_OBJECTS_RE = re.compile(r"\bOBJECTS\s*\{\s*\}")
_HEX_NUMBER_RE = re.compile(r"\b0[xX]([0-9A-Fa-f]+)\b")  # 0xffffffff in a range


def fix_enum_syntax(text: str) -> str:
    """See the module docstring. Works on the comment-stripped text; strings are only touched where a
    quoted enum label is encoded."""
    clean = strip_comments(text)
    fixed = _BAD_LABEL_RE.sub(lambda m: m.group(1) + LABEL_MARK + m.group(2).strip('"').encode().hex(), clean)
    fixed = _HEX_VALUE_RE.sub(lambda m: str(int(m.group(1), 16)), fixed)
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', fixed)
    commas = [m.start() for m in _TRAILING_COMMA_RE.finditer(blanked)]
    if commas:
        fixed = "".join(fixed[a + 1:b] for a, b in zip([-1, *commas], [*commas, len(fixed)]))
    fixed = _BARE_BITS_RE.sub(r"::=\1OCTET STRING", fixed)
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', fixed)
    cuts = [(m.start(), _closing_brace(blanked, m.end() - 1) + 1) for m in _DEFVAL_RE.finditer(blanked)]
    cuts += [m.span(1) for m in _RANGE_AFTER_ENUM_RE.finditer(blanked)]
    cuts += [m.span() for m in _EMPTY_OBJECTS_RE.finditer(blanked)]
    if cuts:
        out, last = [], 0
        for a, b in sorted(cuts):
            if a >= last:
                out.append(fixed[last:a])
                last = b
        fixed = "".join(out) + fixed[last:]
    fixed = _HEX_NUMBER_RE.sub(lambda m: str(int(m.group(1), 16)), fixed)
    return text if fixed == clean else fixed


def _closing_brace(text: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return i
    return len(text) - 1


LC_MARK = "Zmibsitelc"  # prefix that makes a lowercase type name start with a capital while pysmi parses
_LC_TYPE_DEF_RE = re.compile(r"^[ \t]*([a-z][A-Za-z0-9_-]*)[ \t]*::=[ \t\r\n]*SEQUENCE\b(?![ \t\r\n]+OF\b)", re.M)


def mark_lowercase_types(text: str) -> str:
    """Prefix SEQUENCE types this module names in lowercase with LC_MARK where they are used as types:
    their definition, `SEQUENCE OF name` and `SYNTAX name`. The row object of the same name is untouched."""
    clean = strip_comments(text)
    blanked = _STRING_RE.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', clean)
    names = {m.group(1) for m in _LC_TYPE_DEF_RE.finditer(blanked)}
    if not names:
        return text
    alt = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
    pos = [m.start(1) for m in _LC_TYPE_DEF_RE.finditer(blanked)]
    pos += [m.start(1) for m in re.finditer(rf"\b(?:SEQUENCE[ \t\r\n]+OF|SYNTAX)[ \t\r\n]+({alt})(?![A-Za-z0-9_-])", blanked)]
    out, last = [], 0
    for p in sorted(set(pos)):
        out += [clean[last:p], LC_MARK]
        last = p
    out.append(clean[last:])
    return "".join(out)


def unmark(value):
    """Undo lenient's renames (underscores, capitalised names, lowercase types, encoded enum labels)."""
    if isinstance(value, str):
        value = _LABEL_RE.sub(lambda m: bytes.fromhex(m.group(1)).decode(errors="replace"), value)
        value = value.replace(US_MARK, "_").replace(HY_MARK, "-").replace(UC_MARK, "").replace(LC_MARK, "")
        return value.replace(LM_MARK, "")
    if isinstance(value, list):
        return [unmark(v) for v in value]
    if isinstance(value, dict):
        return {unmark(k): unmark(v) for k, v in value.items()}
    return value


_INT32_ENUM_RE = re.compile(r"\b(?:Integer32|Unsigned32)(\s*\{)")


def enum_on_integer32(text: str) -> str:
    """SMIv2 allows named numbers only on INTEGER; vendors write Integer32{up(1), …} too."""
    clean = strip_comments(text)
    if not _INT32_ENUM_RE.search(clean):
        return text
    return _INT32_ENUM_RE.sub(r"INTEGER\1", clean)

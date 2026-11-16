"""Tier 2: net-snmp snmptranslate -Td (the parser LibreNMS itself uses)."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .asn1text import defined_names, parse_imports
from .model import Module, Obj

_CHUNK = 10000  # names per snmptranslate call; each call re-reads the MIBs, so fewer calls are faster
_FIELD = {
    "syntax": r"SYNTAX", "access": r"MAX-ACCESS|ACCESS", "status": r"STATUS",
    "units": r"UNITS", "display_hint": r"DISPLAY-HINT",
}
_KIND = {
    "NOTIFICATION-TYPE": "notification", "TRAP-TYPE": "notification", "MODULE-IDENTITY": "identity",
    "OBJECT-GROUP": "group", "NOTIFICATION-GROUP": "group", "MODULE-COMPLIANCE": "compliance",
}


def _braced(body: str, key: str) -> list[str]:
    m = re.search(rf"^\s*{key}\s+\{{(.*?)\}}", body, re.M | re.S)
    return re.findall(r"[A-Za-z][\w-]*", m.group(1)) if m else []


def _oid(body: str) -> str | None:
    m = re.search(r"::=\s*\{(.*)\}\s*$", body, re.S)
    if not m:
        return None
    inner = m.group(1)
    arcs = re.findall(r"\((\d+)\)", inner)
    parts = inner.split()
    if parts and parts[-1].isdigit():
        arcs.append(parts[-1])
    return ".".join(arcs) or None


def parse_td(text: str) -> list[dict]:
    results = []
    for block in re.split(r"\n\s*\n(?=\S+::\S+\n)", text.strip()):
        lines = block.splitlines()
        if len(lines) < 2 or "::" not in lines[0]:
            continue
        name, _, macro = lines[1].strip().partition(" ")
        body = "\n".join(lines[2:])
        d: dict = {"name": name, "macro": macro.strip()}
        m = re.search(r"--\s*FROM\s+(\S+)", body)
        d["from"] = m.group(1) if m else None
        for key, pat in _FIELD.items():
            m = re.search(rf"^[ \t]*(?:{pat})[ \t]+(.+)$", body, re.M)
            d[key] = m.group(1).strip().strip('"') if m else None
        d["enums"] = None
        if d["syntax"] and "{" in d["syntax"]:
            d["enums"] = {k: int(v) for k, v in re.findall(r"([A-Za-z][\w-]*)\((-?\d+)\)", d["syntax"])} or None
            d["syntax"] = d["syntax"].split("{", 1)[0].strip()
        d["indexes"] = _braced(body, "INDEX")
        aug = _braced(body, "AUGMENTS")
        d["augments"] = aug[0] if aug else None
        d["objects"] = _braced(body, "OBJECTS")
        m = re.search(r'DESCRIPTION\s+"(.*?)"', body, re.S)
        d["description"] = re.sub(r"[ \t]*\n[ \t]*", "\n", m.group(1)).strip() if m else None
        d["oid"] = _oid(body)
        results.append(d)
    return results


def _run(module: str, dirs: list[Path], args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "MIBS": "", "MIBDIRS": ""}
    return subprocess.run(
        ["snmptranslate", "-M", ":".join(map(str, dirs)), "-m", module, *args],
        capture_output=True, text=True, errors="replace", env=env, timeout=600,
    )


def _kind(d: dict) -> str:
    if d["macro"] == "OBJECT-TYPE":
        if (d["syntax"] or "").startswith("SEQUENCE OF"):
            return "table"
        if d["indexes"] or d["augments"]:
            return "row"
        return "scalar"
    return _KIND.get(d["macro"], "node")


def parse_with_netsnmp(name: str, text: str, dir: str, file: str, dirs: list[Path]) -> tuple[Module | None, list[str]]:
    names = defined_names(text)
    if not names:
        return None, ["net-snmp: no definitions found"]
    warnings: list[str] = []
    found: list[dict] = []
    for i in range(0, len(names), _CHUNK):
        chunk = names[i:i + _CHUNK]
        try:
            p = _run(name, dirs, ["-Td", *(f"{name}::{n}" for n in chunk)])
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, [f"net-snmp failed: {e!r}"]
        warnings.extend(line for line in p.stderr.splitlines()
                        if line.strip() and not line.startswith("MIB search path"))
        found.extend(d for d in parse_td(p.stdout) if d["from"] == name and d["oid"])
    warnings = list(dict.fromkeys(warnings))[:50]
    if len(found) < 0.5 * len(names):
        return None, warnings + [f"net-snmp resolved {len(found)} of {len(names)} definitions"]
    mod = Module(name=name, dir=dir, file=file, tier="netsnmp", imports=parse_imports(text))
    rows = {d["oid"] for d in found if _kind(d) == "row"}
    for d in found:
        kind = _kind(d)
        if kind == "scalar" and d["oid"].rsplit(".", 1)[0] in rows:
            kind = "column"
        mod.objects.append(Obj(d["name"], d["oid"], kind, d["syntax"], d["access"], d["status"], d["units"],
                               d["description"], d["indexes"], d["augments"], d["enums"], d["objects"]))
    return mod, warnings

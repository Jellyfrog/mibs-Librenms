from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

from .discover import EXTERNAL_DIR, ROOT_DIR
from .model import Module

IANA_URL = "https://www.iana.org/assignments/enterprise-numbers.txt"
_STANDARDS = [
    ("1.3.6.1.2.", "Standards (IETF)"), ("1.3.6.1.1.", "Standards (IETF)"),
    ("1.3.6.1.3.", "Standards (IETF experimental)"), ("1.3.6.1.5.", "Standards (IETF)"),
    ("1.3.6.1.6.", "Standards (IETF)"), ("1.0.8802.", "Standards (IEEE)"), ("1.3.111.", "Standards (IEEE)"),
    ("1.2.840.10006.", "Standards (IEEE)"), ("0.", "Standards (ITU-T)"),
]


def parse_enterprise_numbers(text: str) -> dict[int, str]:
    lines = text.splitlines()
    result: dict[int, str] = {}
    for i, line in enumerate(lines[:-1]):
        if line.isdigit():
            org = lines[i + 1].strip()
            if org:
                result[int(line)] = org
    return result


def load_enterprises(cache_dir: Path, max_age_days: int = 7) -> dict[int, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / "enterprise-numbers.txt"
    if not f.exists() or time.time() - f.stat().st_mtime > max_age_days * 86400:
        try:
            req = urllib.request.Request(IANA_URL, headers={"User-Agent": "mibsite"})
            with urllib.request.urlopen(req, timeout=60) as r:
                f.write_bytes(r.read())
        except OSError as e:
            print(f"warning: could not download IANA enterprise numbers: {e}")
    return parse_enterprise_numbers(f.read_text(encoding="utf-8", errors="replace")) if f.exists() else {}


def module_root_oid(m: Module) -> str | None:
    for o in m.objects:
        if o.kind == "identity" and o.oid:
            return o.oid
    oids = [o.oid for o in m.objects if o.oid]
    return min(oids, key=lambda x: (x.count("."), x)) if oids else None


def enterprise_number(oid: str | None) -> int | None:
    """N for an OID under 1.3.6.1.4.1.N (IANA private enterprises), else None."""
    arcs = (oid or "").split(".")
    if arcs[:6] == ["1", "3", "6", "1", "4", "1"] and len(arcs) > 6 and arcs[6].isdigit():
        return int(arcs[6])
    return None


def classify(m: Module, enterprises: dict[int, str]) -> str:
    root = module_root_oid(m)
    if root:
        if (n := enterprise_number(root)) in enterprises:
            return enterprises[n]
        for prefix, label in _STANDARDS:
            if (root + ".").startswith(prefix):
                return label
    if m.dir == EXTERNAL_DIR:
        return "External"
    if m.dir == ROOT_DIR:
        return "Other"
    return m.dir.split("/")[0].replace("-", " ").replace("_", " ").title()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unknown"

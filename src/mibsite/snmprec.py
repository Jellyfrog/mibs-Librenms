from __future__ import annotations

import re
from pathlib import Path

from .symbols import SymbolTable

TYPE_NAMES = {"2": "INTEGER", "4": "OCTET STRING", "5": "NULL", "6": "OBJECT IDENTIFIER", "64": "IpAddress",
              "65": "Counter32", "66": "Gauge32", "67": "TimeTicks", "68": "Opaque", "70": "Counter64"}
_MAX_LEN = 200


def humanize_ticks(ticks: int) -> str:
    s = ticks // 100
    return f"{s // 86400}d {s % 86400 // 3600}h {s % 3600 // 60}m {s % 60}s"


def decode_value(tag: str, raw: str) -> tuple[str, str]:
    m = re.match(r"\d+", tag)
    base = m.group(0) if m else tag
    name = TYPE_NAMES.get(base, base)
    if tag.endswith("x"):
        try:
            b = bytes.fromhex(raw)
        except ValueError:
            return name, raw[:_MAX_LEN]
        if base == "64" and len(b) == 4:
            return name, ".".join(str(c) for c in b)
        if b and all(32 <= c < 127 or c in (9, 10, 13) for c in b):
            return name, b.decode("ascii")[:_MAX_LEN]
        text = ":".join(f"{c:02x}" for c in b[:64])
        return name, text + ("…" if len(b) > 64 else "")
    if base == "67" and raw.isdigit():
        return name, f"{raw} ({humanize_ticks(int(raw))})"
    return name, raw[:_MAX_LEN]


def collect_examples(snmprec_dir: Path, table: SymbolTable, limit: int = 3) -> dict[str, dict[str, list[dict]]]:
    result: dict[str, dict[str, list[dict]]] = {}
    for path in sorted(snmprec_dir.glob("*.snmprec")):
        stem = path.stem
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("|", 2)
                if len(parts) != 3:
                    continue
                oid, tag, raw = parts
                hit = table.longest_prefix(oid)
                if hit is None or hit[0] == oid:
                    continue
                matched, entries = hit
                instance = oid[len(matched) + 1:]
                for mod_id, name, kind in entries:
                    if kind not in ("scalar", "column"):
                        continue
                    bucket = result.setdefault(mod_id, {}).setdefault(name, [])
                    if len(bucket) >= limit:
                        continue
                    type_name, value = decode_value(tag, raw)
                    if any(e["v"] == value for e in bucket):
                        continue
                    bucket.append({"v": value, "t": type_name, "i": instance, "f": stem})
    return result

"""Adaptive prefix-sharded static search index (format v2).

Layout under data/search/:
  manifest.json  {"v":2, "dirs":[...], "vendors":[...], "modules":[[name, dirIdx, vendorIdx]],
                  "n": front-coded name-shard prefixes, "o": front-coded OID-shard prefixes}
  n/<prefix>.txt one line per (name, oid):   name TAB oid-or-empty TAB modIdx[,modIdx...]
  o/<prefix>.txt one line per (oid, name):   oid-relative-to-prefix TAB name TAB modIdx[,modIdx...]
A module URL is /mib/<dir>/<name>/. Front coding: entries joined by newline, each "<shared chars> <rest>"
relative to the previous entry. Everything here exists to keep the files (and first search) small.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .model import Module
from .symbols import oid_key


def extend_chars(key: str, prefix: str) -> str | None:
    return key[: len(prefix) + 1] if len(key) > len(prefix) else None


def extend_arcs(key: str, prefix: str) -> str | None:
    arcs = key.split(".")
    n = prefix.count(".") + 1 if prefix else 0
    return ".".join(arcs[: n + 1]) if len(arcs) > n else None


def build_shards(entries, extend, max_bytes: int = 50_000, max_depth: int = 24,
                 saving: Callable[[str, str], int] = lambda prefix, key: 0) -> dict[str, list]:
    """Split (key, row, nbytes) entries, sorted by key, into prefix shards of at most `max_bytes`.

    `nbytes` is the row's encoded size measured once up front with the full key; `saving(prefix, key)` is
    how many bytes a row saves inside a shard with that prefix (OID shards store OIDs relative to it). It
    depends only on whether key == prefix, so it is evaluated twice per level instead of once per row:
    re-encoding every row at every split level made this step take ~25 s.
    """
    shards: dict[str, list] = {}

    def size(prefix: str, items: list) -> int:
        equal = 0  # rows whose key is the prefix itself sort first
        while equal < len(items) and items[equal][0] == prefix:
            equal += 1
        other = saving(prefix, prefix + ".0") if len(items) > equal else 0
        return (sum(n for _, _, n in items) - (len(items) - equal) * other
                - (equal * saving(prefix, prefix) if equal else 0))

    def rec(prefix: str, items: list, depth: int) -> None:
        if depth >= max_depth or size(prefix, items) <= max_bytes:
            shards[prefix] = [r for _, r, _ in items]
            return
        groups: dict[str, list] = defaultdict(list)
        here = []
        for item in items:
            nxt = extend(item[0], prefix)
            (groups[nxt] if nxt is not None else here).append(item)
        if here:
            shards[prefix] = [r for _, r, _ in here]
        for p in sorted(groups):
            rec(p, groups[p], depth + 1)

    rec("", list(entries), 0)
    return shards


def shard_filename(prefix: str) -> str:
    return prefix or "_"


def relative_oid(oid: str, prefix: str) -> str:
    """OID with the shard prefix (whole arcs) removed; "" when it is the prefix itself."""
    if not prefix:
        return oid
    return "" if oid == prefix else oid[len(prefix) + 1:]


def _line(a: str, b: str, idx: list[int]) -> str:
    return f"{a}\t{b}\t{','.join(map(str, idx))}\n"


def encode_names(prefix: str, rows: list) -> str:
    return "".join(_line(name, oid or "", idx) for name, oid, idx in rows)


def encode_oids(prefix: str, rows: list) -> str:
    return "".join(_line(relative_oid(oid, prefix), name, idx) for oid, name, idx in rows)


def front_code(items: list[str]) -> str:
    out, prev = [], ""
    for s in items:
        k = 0
        while k < min(len(s), len(prev)) and s[k] == prev[k]:
            k += 1
        out.append(f"{k} {s[k:]}")
        prev = s
    return "\n".join(out)


def _grouped(entries: list[tuple[str, tuple]]) -> list[tuple[str, list, int]]:
    """Merge entries with the same (key, a, b) into one row listing every module index; attach its size."""
    merged: dict[tuple, list[int]] = {}
    for key, (a, b, idx) in entries:
        merged.setdefault((key, a, b), []).append(idx)
    return [(key, [a, b, idxs], len(_line(a, b or "", idxs))) for (key, a, b), idxs in merged.items()]


def _write(dir_: Path, shards: dict[str, list], encode) -> list[str]:
    dir_.mkdir(parents=True, exist_ok=True)
    for prefix, rows in shards.items():
        (dir_ / f"{shard_filename(prefix)}.txt").write_text(encode(prefix, rows))
    return sorted(shards)


def write_search_index(out_dir: Path, modules: list[Module], vendors: dict[str, str], max_bytes: int = 50_000) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    mods = sorted(modules, key=lambda m: (m.name.lower(), m.id))
    name_entries, oid_entries = [], []
    for idx, m in enumerate(mods):
        name_entries.append((m.name.lower(), (m.name, None, idx)))
        if not m.shows_objects:
            continue  # its page shows no objects, so object links would lead nowhere
        for o in m.objects:
            name_entries.append((o.name.lower(), (o.name, o.oid or "-", idx)))  # "-": object without OID
            if o.oid:
                oid_entries.append((o.oid, (o.oid, o.name, idx)))
    name_entries.sort(key=lambda e: (e[0], e[1][0], e[1][1] or "", e[1][2]))
    oid_entries.sort(key=lambda e: (oid_key(e[0]), e[1][1], e[1][2]))

    dirs = sorted({m.dir for m in mods})
    vendor_names = sorted({vendors.get(m.id, "") for m in mods})
    d_idx = {d: i for i, d in enumerate(dirs)}
    v_idx = {v: i for i, v in enumerate(vendor_names)}
    n_prefixes = _write(out_dir / "n", build_shards(_grouped(name_entries), extend_chars, max_bytes), encode_names)
    o_prefixes = _write(out_dir / "o", build_shards(_grouped(oid_entries), extend_arcs, max_bytes,
                                                    saving=lambda p, k: len(k) - len(relative_oid(k, p))), encode_oids)
    manifest = {
        "v": 2,
        "dirs": dirs,
        "vendors": vendor_names,
        "modules": [[m.name, d_idx[m.dir], v_idx[vendors.get(m.id, "")]] for m in mods],
        "n": front_code(n_prefixes),
        "o": front_code(o_prefixes),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":"), ensure_ascii=False))
    return manifest

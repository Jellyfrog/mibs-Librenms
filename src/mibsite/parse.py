"""Tier orchestration, parallel parsing and on-disk cache."""
from __future__ import annotations

import hashlib
import subprocess
import json
import os
from multiprocessing import Pool
from pathlib import Path

from . import PARSER_VERSION
from .aliases import resolve_module
from .asn1text import parse_imports, read_text, split_modules
from .discover import MibFile, all_dirs, search_dirs
from .model import Module
from .parse_netsnmp import parse_with_netsnmp
from .parse_pysmi import BASE_MIBS, MAX_MIB_BYTES, compile_pysmi, normalize_pysmi
from .parse_regex import parse_with_regex
from .progress import Progress

# files this large go straight to net-snmp (the reader's maxMibSize)
PYSMI_MAX_BYTES = MAX_MIB_BYTES


def parse_file(mf: MibFile, dirs: list[Path], available: set[str]) -> list[Module]:
    text = read_text(mf.path)
    if not mf.modules:
        return [Module(name=mf.path.name, dir=mf.dir, file=mf.rel, tier="raw",
                       errors=["No ASN.1 module definition (DEFINITIONS ::= BEGIN) found"])]
    single = len(mf.modules) == 1
    too_big_for_pysmi = mf.path.stat().st_size >= PYSMI_MAX_BYTES
    result = []
    for name, segment in split_modules(text):
        errors: list[str] = []
        if too_big_for_pysmi:
            errors.append(f"pysmi skipped: file is {mf.path.stat().st_size // 1_000_000} MB (pysmi limit 10 MB)")
        elif single and mf.path.name == name and name not in BASE_MIBS:
            js, messages = compile_pysmi(name, dirs, available)
            if js is not None:
                mod = normalize_pysmi(js, name, mf.dir, mf.rel)
                mod.errors = messages
                result.append(mod)
                continue
            errors.extend(messages)
        elif name not in BASE_MIBS:
            errors.append("pysmi skipped: file name differs from module name or file has several modules")
        mod, warnings = parse_with_netsnmp(name, segment, mf.dir, mf.rel, dirs)
        errors.extend(warnings)
        if mod is None:
            mod = parse_with_regex(name, segment, mf.dir, mf.rel)
        if mod is None:
            mod = Module(name=name, dir=mf.dir, file=mf.rel, tier="raw", imports=parse_imports(segment))
        mod.errors = errors
        result.append(mod)
    return result


def _snmptranslate_version() -> str:
    """e.g. "NET-SNMP version: 5.10.rc1" — part of the cache key, as the net-snmp tier depends on it."""
    try:
        p = subprocess.run(["snmptranslate", "-V"], capture_output=True, text=True, timeout=30)
        return (p.stdout + p.stderr).strip()
    except OSError:
        return "no snmptranslate"


def cache_keys(files: list[MibFile], available: set[str]) -> dict[tuple[str, str], str]:
    """Per-file cache key = parser version + path + the file's own bytes + which of its imports exist.

    Like `git diff` on the MIB tree, but needs no stored commit or git history: only files whose bytes
    changed are re-parsed. Dependents are not invalidated on purpose: SMI forbids re-assigning an existing
    OID, so editing a MIB cannot change what its importers resolve. The one case that can is an import
    that was missing and now exists (or vice versa); that flips the "exists" bit and re-parses the importer.
    """
    keys = {}
    tool = _snmptranslate_version()
    for f in files:
        data = f.path.read_bytes()
        h = hashlib.sha256(f"{PARSER_VERSION}\0{tool}\0{f.dir}\0{f.rel}\0".encode())
        h.update(hashlib.sha256(data).digest())
        if len(data) >= 10_000_000:  # pysmi's default limit: a new limit re-parses only these few large files
            h.update(f"pysmi limit {PYSMI_MAX_BYTES}\0".encode())
        if f.modules:
            for name in sorted(parse_imports(read_text(f.path))):
                h.update(f"{name}={resolve_module(name, available) in available}\0".encode())
        keys[(f.dir, f.rel)] = h.hexdigest()
    return keys


_STATE: dict = {}


def _init(mibs_root, extra_root, dirs, available):
    _STATE.update(mibs_root=mibs_root, extra_root=extra_root, dirs=dirs, available=available)


def _work(mf: MibFile) -> tuple[tuple[str, str], list[dict], bool]:
    """Parse one file in a worker. Returns (file id, module dicts, cacheable)."""
    s = _STATE
    try:
        mods = parse_file(mf, search_dirs(mf, s["mibs_root"], s["extra_root"], s["dirs"]), s["available"])
        ok = True
    except Exception as e:  # last-resort guard: never lose a page, but don't pin a transient failure in the cache
        mods = [Module(name=(mf.modules or (mf.path.name,))[0], dir=mf.dir, file=mf.rel, tier="raw",
                       errors=[f"internal error: {e!r}"])]
        ok = False
    return (mf.dir, mf.rel), [m.to_dict() for m in mods], ok


def _store(path: Path, data: list[dict]) -> None:
    """Atomic cache write: an interrupted build never leaves a truncated entry behind."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def _load(path: Path) -> list[dict] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):  # missing or damaged entry: treat as a miss
        return None


def parse_all(files: list[MibFile], mibs_root: Path, extra_root: Path | None, jobs: int | None,
              cache_dir: Path | None, available: set[str] | None = None,
              all_files: list[MibFile] | None = None) -> list[Module]:
    """Parse files, reusing cached results (see cache_keys); only cache misses go to the worker pool.
    `available`/`all_files` describe every MIB on disk (default: just `files`)."""
    if available is None:
        available = {m for f in files for m in f.modules}
    cache: dict[tuple[str, str], Path] = {}
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = {fid: cache_dir / f"{k}.json" for fid, k in cache_keys(files, available).items()}
    hits, misses = [], []
    for f in files:
        c = cache.get((f.dir, f.rel))
        (hits if c is not None and c.exists() else misses).append(f)
    results: dict[tuple[str, str], list[dict]] = {}
    pool = None
    print(f"  {len(hits):,} from cache, {len(misses):,} to parse", flush=True)
    progress = Progress("parsed", len(misses))

    def start(todo: list[MibFile]):
        nonlocal pool
        if pool is None:
            args = (mibs_root, extra_root, all_dirs(mibs_root), available)
            pool = Pool(max(1, min(jobs or os.cpu_count() or 1, len(todo))), initializer=_init, initargs=args)
        # biggest files first so a slow one never becomes the last straggler
        return pool.imap_unordered(_work, sorted(todo, key=lambda f: f.path.stat().st_size, reverse=True), chunksize=1)

    def drain(pending) -> None:
        # cache each result as it arrives, so an interrupted cold build keeps everything finished so far
        for fid, data, ok in pending:
            results[fid] = data
            if ok and fid in cache:
                _store(cache[fid], data)
            progress.step()

    try:
        # fork the workers before loading cached results, so they don't inherit (and copy) that heap
        pending = start(misses) if misses else ()
        damaged = []
        for f in hits:
            data = _load(cache[(f.dir, f.rel)])
            if data is None:
                damaged.append(f)
            else:
                results[(f.dir, f.rel)] = data
        drain(pending)
        if misses:
            progress.close()
        if damaged:
            drain(start(damaged))
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    if cache and all_files is not None and len(files) == len(all_files):
        live = {c.name for c in cache.values()}  # full build: drop entries (and stray temp files) no file uses
        for p in cache_dir.iterdir():
            if p.name not in live:
                p.unlink()
    return [Module.from_dict(d) for f in files for d in results[(f.dir, f.rel)]]

"""Download public MIBs that LibreNMS MIBs import but LibreNMS does not ship."""
from __future__ import annotations

import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from .aliases import resolve_module
from .asn1text import detect_modules, parse_imports, read_text, split_modules
from .discover import MibFile, discover

PUBLIC_SOURCE = "https://raw.githubusercontent.com/lextudio/mibs.pysnmp.com/master/asn1/{name}"


def _http(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "mibsite"}), timeout=30) as r:
            return r.read()
    except (urllib.error.URLError, OSError):
        return None


def missing_imports(files: list[MibFile]) -> dict[str, int]:
    available = {m for f in files for m in f.modules}
    counts: Counter[str] = Counter()
    for f in files:
        wanted: set[str] = set()
        for _, segment in split_modules(read_text(f.path)):
            wanted.update(parse_imports(segment))
        for mod in wanted:
            if resolve_module(mod, available) not in available:
                counts[mod] += 1
    return dict(counts)


def fetch_extra(mibs_root: Path, extra_root: Path, fetch=None, rounds: int = 5) -> dict:
    fetch = fetch or _http
    extra_root.mkdir(parents=True, exist_ok=True)
    downloaded: dict[str, str] = {}
    tried: set[str] = set()
    missing: dict[str, int] = {}
    for _ in range(rounds):
        missing = missing_imports(discover(mibs_root, extra_root))
        todo = sorted(set(missing) - tried)
        if not todo:
            break
        for name in todo:
            tried.add(name)
            url = PUBLIC_SOURCE.format(name=name)
            data = fetch(url)
            if data and name in detect_modules(data.decode("utf-8", errors="replace")):
                (extra_root / name).write_bytes(data)
                downloaded[name] = url
                print(f"downloaded {name}")
    unresolved = {k: v for k, v in missing.items() if k not in downloaded}
    lines = ["# External MIBs", "",
             "Public MIBs imported by LibreNMS MIBs but not shipped with LibreNMS. "
             "Regenerate with `uv run mibsite fetch-extra`.",
             "", "| Module | Source |", "|---|---|"]
    existing = sorted(p.name for p in extra_root.iterdir() if p.is_file() and p.suffix != ".md")
    lines += [f"| {n} | {downloaded.get(n, PUBLIC_SOURCE.format(name=n))} |" for n in existing]
    lines += ["", "## Still unresolved", ""]
    lines += [f"- {k} (imported by {v} file(s))" for k, v in sorted(unresolved.items())]
    (extra_root / "SOURCES.md").write_text("\n".join(lines) + "\n")
    return {"downloaded": sorted(downloaded), "unresolved": unresolved}

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .asn1text import detect_modules, read_text
from .model import EXTERNAL_DIR, ROOT_DIR

_SKIP_SUFFIXES = {".md"}


@dataclass(frozen=True)
class MibFile:
    path: Path
    rel: str
    dir: str
    modules: tuple[str, ...]


def _files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() not in _SKIP_SUFFIXES:
            yield p


def discover(mibs_root: Path, extra_root: Path | None) -> list[MibFile]:
    out: list[MibFile] = []
    for root, external in ((mibs_root, False), (extra_root, True)):
        if root is None or not root.is_dir():
            continue
        for p in _files(root):
            if external:
                d = EXTERNAL_DIR
            elif p.parent == root:
                d = ROOT_DIR
            else:
                d = p.parent.relative_to(root).as_posix()
            out.append(MibFile(p, p.relative_to(root).as_posix(), d, tuple(detect_modules(read_text(p)))))
    return out


def all_dirs(root: Path) -> list[Path]:
    return sorted([root, *(p for p in root.rglob("*") if p.is_dir())])


def search_dirs(mf: MibFile, mibs_root: Path, extra_root: Path | None, dirs: list[Path]) -> list[Path]:
    return list(dict.fromkeys([mf.path.parent, mibs_root, *([extra_root] if extra_root else []), *dirs]))

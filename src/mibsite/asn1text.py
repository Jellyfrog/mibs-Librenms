"""Lightweight, tolerant helpers over raw ASN.1/SMI text."""
from __future__ import annotations

import re
from pathlib import Path

_HEADER_RE = re.compile(r"\bDEFINITIONS\s*(?:IMPLICIT\s+TAGS\s*)?::=\s*BEGIN")
_NAME_BEFORE_RE = re.compile(r"([A-Za-z][A-Za-z0-9_-]*)\s+$")
_IMPORTS_RE = re.compile(r"\bIMPORTS\b(.*?);", re.S)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_DEF_RE = re.compile(
    r"^[ \t]*([a-z][A-Za-z0-9_-]*)\s+"
    r"(OBJECT-TYPE|OBJECT\s+IDENTIFIER|NOTIFICATION-TYPE|MODULE-IDENTITY|OBJECT-IDENTITY|"
    r"TRAP-TYPE|OBJECT-GROUP|NOTIFICATION-GROUP|MODULE-COMPLIANCE|AGENT-CAPABILITIES)\b",
    re.M,
)


def read_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


_STR_OR_COMMENT_RE = re.compile(r'"[^"]*"|--[^\n]*?(?:--|$)', re.M)


def strip_comments(text: str) -> str:
    """Remove ASN.1 comments (`--` to end of line or to the next `--`), leaving quoted strings intact."""
    return _STR_OR_COMMENT_RE.sub(lambda m: m.group(0) if m.group(0)[0] == '"' else "", text)


def _module_headers(clean: str) -> list[tuple[str, int]]:
    """(module name, header start offset) for each `NAME DEFINITIONS ::= BEGIN` in comment-free text."""
    found = []
    for m in _HEADER_RE.finditer(clean):
        before = _NAME_BEFORE_RE.search(clean[max(0, m.start() - 200):m.start()])
        if before:
            found.append((before.group(1), m.start() - len(before.group(0))))
    return found


def detect_modules(text: str) -> list[str]:
    return [name for name, _ in _module_headers(strip_comments(text))]


def split_modules(text: str) -> list[tuple[str, str]]:
    """Split comment-stripped text into (module name, module text) segments."""
    clean = strip_comments(text)
    headers = _module_headers(clean)
    parts = []
    for i, (name, start) in enumerate(headers):
        end = headers[i + 1][1] if i + 1 < len(headers) else len(clean)
        parts.append((name, clean[start:end]))
    return parts


def parse_imports(text: str) -> dict[str, list[str]]:
    m = _IMPORTS_RE.search(strip_comments(text))
    if not m:
        return {}
    tokens = _TOKEN_RE.findall(m.group(1))
    result: dict[str, list[str]] = {}
    pending: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "FROM" and i + 1 < len(tokens):
            result.setdefault(tokens[i + 1], []).extend(pending)
            pending = []
            i += 2
        else:
            pending.append(tokens[i])
            i += 1
    return result


def defined_names(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for name, _ in _DEF_RE.findall(strip_comments(text)):
        seen.setdefault(name, None)
    return list(seen)


_DEF_START_RE = re.compile(
    r"^[ \t]*(?!(?:SYNTAX|WRITE-SYNTAX|IDENTIFIER)\b)([A-Za-z][A-Za-z0-9_-]*)[ \t]+(?:OBJECT\s+IDENTIFIER|OBJECT-TYPE|OBJECT-IDENTITY|NOTIFICATION-TYPE"
    r"|TRAP-TYPE|OBJECT-GROUP|NOTIFICATION-GROUP|MODULE-COMPLIANCE|MODULE-IDENTITY|AGENT-CAPABILITIES)\b"
    r"|^[ \t]*(?!IDENTIFIER\b)([A-Za-z][A-Za-z0-9_-]*)[ \t]*::=", re.M)
_DESCRIPTION_RE = re.compile(r'\bDESCRIPTION\s*"([^"]*)"')


def _layout(raw: str) -> str:
    """A DESCRIPTION string as the MIB lays it out: its line breaks kept, the shared indentation of the
    continuation lines removed, trailing whitespace dropped."""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rest = [ln.rstrip() for ln in lines[1:]]
    indent = min((len(ln) - len(ln.lstrip()) for ln in rest if ln.strip()), default=0)
    out = [lines[0].strip()] + [ln[indent:] for ln in rest]
    while out and not out[-1]:
        out.pop()
    while out and not out[0]:
        out.pop(0)
    return "\n".join(out)


def raw_descriptions(text: str) -> dict[str, str]:
    """name -> its DESCRIPTION as written in the MIB (first one per definition)."""
    clean = strip_comments(text)
    starts = list(_DEF_START_RE.finditer(clean))
    out: dict[str, str] = {}
    for m, nxt in zip(starts, starts[1:] + [None]):
        name = m.group(1) or m.group(2)
        d = _DESCRIPTION_RE.search(clean, m.end(), nxt.start() if nxt else len(clean))
        if d and name not in out:
            out[name] = _layout(d.group(1))
    return out

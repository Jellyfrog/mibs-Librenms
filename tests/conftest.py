from pathlib import Path
import shutil

import pytest

needs_netsnmp = pytest.mark.skipif(not shutil.which("snmptranslate"), reason="net-snmp not installed")
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


from html import escape as _esc
from html.parser import HTMLParser


class _Canon(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out = []

    def handle_starttag(self, tag, attrs):
        a = "".join(f' {k}' if v is None else f' {k}="{_esc(v, quote=True)}"' for k, v in sorted(attrs))
        self.out.append(f"<{tag}{a}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(data)

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")


def canon(html: str) -> str:
    """Pages are minified (unquoted, reordered attributes); compare against this canonical form instead:
    every start tag re-serialized with sorted, double-quoted attributes."""
    p = _Canon()
    p.feed(html)
    p.close()
    return "".join(p.out)

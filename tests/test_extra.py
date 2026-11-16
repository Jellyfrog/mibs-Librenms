from mibsite.discover import discover
from mibsite.extra import missing_imports, fetch_extra


def test_missing_imports(fixtures_dir):
    miss = missing_imports(discover(fixtures_dir / "mibs", None))
    assert miss == {"NONEXISTENT-MIB": 1}


def test_fetch_extra(tmp_path):
    mibs = tmp_path / "mibs"; mibs.mkdir()
    (mibs / "A-MIB").write_text("A-MIB DEFINITIONS ::= BEGIN\nIMPORTS x FROM B-MIB y FROM RFC-1213 z FROM GONE-MIB;\nEND\n")
    (mibs / "RFC1213-MIB").write_text("RFC1213-MIB DEFINITIONS ::= BEGIN\nEND\n")
    remote = {
        "B-MIB": b"B-MIB DEFINITIONS ::= BEGIN\nIMPORTS q FROM C-MIB;\nEND\n",
        "C-MIB": b"C-MIB DEFINITIONS ::= BEGIN\nEND\n",
    }
    calls = []

    def fake(url):
        calls.append(url)
        return remote.get(url.rsplit("/", 1)[1])

    extra = tmp_path / "extra"
    report = fetch_extra(mibs, extra, fetch=fake)
    assert sorted(report["downloaded"]) == ["B-MIB", "C-MIB"]
    assert report["unresolved"] == {"GONE-MIB": 1}
    assert (extra / "C-MIB").exists()
    src = (extra / "SOURCES.md").read_text()
    assert "B-MIB" in src and "lextudio" in src and "GONE-MIB" in src
    assert not any(u.endswith("/RFC-1213") for u in calls)

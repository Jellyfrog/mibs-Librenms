import json
import shutil
import pytest
from mibsite.build import build, safe_clean


def _fake_librenms(fixtures_dir, tmp_path):
    lib = tmp_path / "librenms"
    shutil.copytree(fixtures_dir / "mibs", lib / "mibs")
    shutil.copytree(fixtures_dir / "snmpsim", lib / "tests" / "snmpsim")
    return lib


def test_safe_clean_refuses_foreign_dir(tmp_path):
    (tmp_path / "important.txt").write_text("x")
    with pytest.raises(SystemExit):
        safe_clean(tmp_path)
    assert (tmp_path / "important.txt").exists()


def test_build_end_to_end(fixtures_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("mibsite.build.load_enterprises", lambda cache: {99999: "Example Org"})
    lib = _fake_librenms(fixtures_dir, tmp_path)
    out = tmp_path / "site"
    stats = build(lib, out, "https://mibs.example.org", jobs=2, only=None, extra=None, cache=tmp_path / "cache")
    assert stats["modules"] >= 6
    page = (out / "mib/GOOD-MIB/index.html").read_text()
    assert "Example Org" in page
    assert (out / "vendors/example-org/index.html").exists()
    assert "widget-1" in page  # snmprec example rendered into the page
    assert not (out / "data/examples").exists()
    man = json.loads((out / "data/search/manifest.json").read_text())
    assert any(m[0] == "GOOD-MIB" for m in man["modules"])
    assert (out / "mib/acme/NOT-A-MIB/index.html").exists()
    # rebuild into the same dir is allowed (marker present)
    build(lib, out, "https://mibs.example.org", jobs=2, only="GOOD-MIB", extra=None, cache=tmp_path / "cache")
    assert not (out / "mib/acme/NOT-A-MIB/index.html").exists()

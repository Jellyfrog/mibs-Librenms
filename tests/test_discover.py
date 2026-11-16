from mibsite.discover import discover, all_dirs, search_dirs, ROOT_DIR


def test_discover(fixtures_dir):
    root = fixtures_dir / "mibs"
    files = {f.rel: f for f in discover(root, None)}
    assert files["GOOD-MIB"].dir == ROOT_DIR
    assert files["GOOD-MIB"].modules == ("GOOD-MIB",)
    assert files["acme/BROKEN-IMPORT-MIB"].dir == "acme"
    assert files["acme/NOT-A-MIB"].modules == ()
    assert files["acme/TWO-MODULES"].modules == ("FIRST-MIB", "SECOND-MIB")


def test_discover_external(fixtures_dir, tmp_path):
    (tmp_path / "X-MIB").write_text("X-MIB DEFINITIONS ::= BEGIN\nEND\n")
    (tmp_path / "SOURCES.md").write_text("# sources\n")
    files = [f for f in discover(fixtures_dir / "mibs", tmp_path) if f.dir == "_external"]
    assert [f.rel for f in files] == ["X-MIB"]


def test_search_dirs_order(fixtures_dir, tmp_path):
    root = fixtures_dir / "mibs"
    dirs = all_dirs(root)
    mf = next(f for f in discover(root, None) if f.rel == "acme/BROKEN-IMPORT-MIB")
    order = search_dirs(mf, root, tmp_path, dirs)
    assert order[:3] == [root / "acme", root, tmp_path]
    assert len(order) == len(set(order))

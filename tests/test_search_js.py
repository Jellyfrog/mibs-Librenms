from conftest import needs_node
import json
import subprocess
from pathlib import Path

JS = Path(__file__).parents[1] / "src/mibsite/static/search.js"


@needs_node
def test_js_helpers():
    script = f"""
const s = require({json.dumps(str(JS))});
const out = {{
  names: s.pickNameShards(["", "i", "if", "ifi", "ip"], "if"),
  namesShort: s.pickNameShards(["", "i", "if", "ifi", "ip"], "i"),
  oids: s.pickOidShards(["", "1.3.6.1", "1.3.6.1.2.1.2", "1.3.6.1.4"], "1.3.6.1.2.1.2.2.1.10.5"),
  look: s.oidLookup([["1.3.6.1.2.1.2.2.1", "ifEntry", 0, "row"], ["1.3.6.1.2.1.2.2.1.10", "ifInOctets", 0, "column"]],
                    "1.3.6.1.2.1.2.2.1.10.5"),
}};
console.log(JSON.stringify(out));
"""
    res = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert res["names"] == ["if", "ifi"]
    assert res["namesShort"] == ["i", "if", "ip", "ifi"]  # shortest prefixes first
    assert res["oids"] == ["1.3.6.1.2.1.2", "1.3.6.1", ""]
    assert res["look"]["best"][1] == "ifInOctets" and res["look"]["instance"] == "5"


@needs_node
def test_js_decodes_python_index(tmp_path):
    from mibsite.model import Module, Obj
    from mibsite.search_index import write_search_index
    objs = [Obj(f"o{i}", f"1.3.6.1.4.1.9.{i}", "scalar") for i in range(300)] + [Obj("ifInOctets", "1.3.6.1.2.1.2.2.1.10", "column"),
            Obj("noOid", None, "scalar")]
    write_search_index(tmp_path, [Module("BIG-MIB", "acme", "acme/BIG-MIB", "pysmi", objects=objs)], {}, max_bytes=2_000)
    o_prefixes = sorted(p.stem if p.stem != "_" else "" for p in (tmp_path / "o").iterdir())
    script = f"""
const fs = require("fs"), s = require({json.dumps(str(JS))});
const dir = {json.dumps(str(tmp_path))};
const man = JSON.parse(fs.readFileSync(dir + "/manifest.json", "utf8"));
const o = s.frontDecode(man.o), n = s.frontDecode(man.n);
const rows = [];
o.forEach(p => rows.push(...s.parseOids(p, fs.readFileSync(dir + "/o/" + (p || "_") + ".txt", "utf8"))));
const names = [];
n.forEach(p => names.push(...s.parseNames(fs.readFileSync(dir + "/n/" + (p || "_") + ".txt", "utf8"))));
console.log(JSON.stringify({{o, rows, names}}));
"""
    res = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert res["o"] == o_prefixes
    assert sorted(r[0] for r in res["rows"]) == sorted(o.oid for o in objs if o.oid)
    assert ["noOid", None, 0, False] in res["names"]  # an object without OID is not shown as a MIB
    assert ["o42", "1.3.6.1.4.1.9.42", 0, False] in res["names"] and ["BIG-MIB", None, 0, True] in res["names"]

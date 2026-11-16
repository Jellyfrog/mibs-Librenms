from conftest import needs_netsnmp
from mibsite.discover import all_dirs
from mibsite.parse_netsnmp import parse_td, parse_with_netsnmp

TD = '''IF-MIB::ifEntry
ifEntry OBJECT-TYPE
  -- FROM	IF-MIB
  MAX-ACCESS	not-accessible
  STATUS	current
  INDEX		{ ifIndex }
  DESCRIPTION	"An entry containing management information applicable to a
            particular interface."
::= { iso(1) org(3) dod(6) internet(1) mgmt(2) mib-2(1) interfaces(2) ifTable(2) 1 }

IF-MIB::ifAdminStatus
ifAdminStatus OBJECT-TYPE
  -- FROM	IF-MIB
  SYNTAX	INTEGER {up(1), down(2), testing(3)} 
  MAX-ACCESS	read-write
  STATUS	current
  UNITS		"seconds"
  DESCRIPTION	"The desired state."
::= { iso(1) org(3) dod(6) internet(1) mgmt(2) mib-2(1) interfaces(2) ifTable(2) ifEntry(1) 7 }
'''


def test_parse_td():
    a, b = parse_td(TD)
    assert a["name"] == "ifEntry" and a["macro"] == "OBJECT-TYPE" and a["from"] == "IF-MIB"
    assert a["oid"] == "1.3.6.1.2.1.2.2.1" and a["indexes"] == ["ifIndex"]
    assert a["description"] == "An entry containing management information applicable to a\nparticular interface."
    assert b["syntax"] == "INTEGER" and b["enums"] == {"up": 1, "down": 2, "testing": 3}
    assert b["units"] == "seconds" and b["oid"] == "1.3.6.1.2.1.2.2.1.7"


@needs_netsnmp
def test_broken_import_mib(fixtures_dir):
    root = fixtures_dir / "mibs"
    path = root / "acme/BROKEN-IMPORT-MIB"
    mod, warnings = parse_with_netsnmp("BROKEN-IMPORT-MIB", path.read_text(), "acme", "acme/BROKEN-IMPORT-MIB",
                                       [root / "acme", *all_dirs(root)])
    assert mod is not None and mod.tier == "netsnmp"
    objs = {o.name: o for o in mod.objects}
    assert objs["acmeTemp"].oid == "1.3.6.1.4.1.99998.1"
    assert objs["acmeTemp"].kind == "scalar" and objs["acmeTemp"].access == "read-only"
    assert "SNMPv2-SMI" in mod.imports
    assert any("NONEXISTENT-MIB" in w for w in warnings)

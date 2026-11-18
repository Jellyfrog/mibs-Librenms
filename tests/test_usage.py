from mibsite.model import Module, Obj
from mibsite.usage import collect_usage


def _mods():
    a = Module("ACME-MIB", "acme", "acme/ACME-MIB", "pysmi", objects=[
        Obj("acme", "1.3.6.1.4.1.9", "node"), Obj("acmeTemp", "1.3.6.1.4.1.9.1", "scalar"),
        Obj("acmeTable", "1.3.6.1.4.1.9.3", "table"), Obj("acmeEntry", "1.3.6.1.4.1.9.3.1", "row"),
        Obj("acmeIfName", "1.3.6.1.4.1.9.3.1.2", "column")])
    b = Module("ACME-MIB", "other", "other/ACME-MIB", "pysmi", objects=[Obj("acmeFan", "1.3.6.1.4.1.9.2", "scalar")])
    c = Module("OTHER-MIB", "x", "x/OTHER-MIB", "pysmi")
    lan = Module("LAN", "y", "y/LAN", "pysmi")
    return [a, b, c, lan]


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_mib_object_references_ignore_php_static_calls(tmp_path):
    _write(tmp_path, "resources/definitions/os_discovery/acme.yaml",
           "oid: ACME-MIB::acmeTemp.0\nvalue: ACME-MIB::acmeFan\nbad: ACME-MIB::nope\n")
    _write(tmp_path, "LibreNMS/Acme.php", "<?php Str::of('x'); SnmpQuery::get('ACME-MIB::acmeTemp.0');")
    u = collect_usage(tmp_path, _mods())
    # each object is credited to the copy that defines it; unknown objects and PHP classes are ignored
    assert u.objects == {"acme/ACME-MIB": {"acmeTemp"}, "other/ACME-MIB": {"acmeFan"}}
    assert u.by_ref == {"acme/ACME-MIB", "other/ACME-MIB"}


def test_mib_name_alone_counts_but_not_plain_words(tmp_path):
    _write(tmp_path, "resources/definitions/os_discovery/x.yaml", "mib: OTHER-MIB\nport: LAN\n")
    u = collect_usage(tmp_path, _mods())
    assert u.by_name == {"x/OTHER-MIB"}  # "LAN" is a MIB name too, but also a plain word


def test_numeric_oids_map_to_the_data_object_they_belong_to(tmp_path):
    _write(tmp_path, "includes/acme.inc.php",
           "<?php snmp_get($d, '.1.3.6.1.4.1.9.1.0'); snmpwalk('1.3.6.1.4.1.9.3.1.2.17'); snmp_get($d, '.1.3.6.1.4.1.9.99.0');")
    u = collect_usage(tmp_path, _mods())
    # .9.99 sits under the vendor node only: plain nodes do not count
    assert u.objects == {"acme/ACME-MIB": {"acmeTemp", "acmeIfName"}}
    assert u.by_oid == {"acme/ACME-MIB"}


def test_quoted_object_names_count_for_a_mib_named_in_the_same_file(tmp_path):
    _write(tmp_path, "includes/a.inc.php", "<?php snmpwalk_cache_oid($device, 'acmeTemp', [], 'OTHER-MIB');")
    _write(tmp_path, "includes/b.inc.php", "<?php snmpwalk_cache_oid($device, 'acmeIfName', [], 'ACME-MIB');")
    u = collect_usage(tmp_path, _mods())
    # acmeTemp is no OTHER-MIB object: it still counts, but as a bare name only ACME-MIB defines
    assert u.objects == {"acme/ACME-MIB": {"acmeIfName", "acmeTemp"}}
    assert u.by_name == {"x/OTHER-MIB", "acme/ACME-MIB"}


def test_mib_dir_decides_which_copy_gets_the_credit(tmp_path):
    mods = _mods() + [Module("ACME-MIB", "acme2", "acme2/ACME-MIB", "pysmi",
                             objects=[Obj("acmeTemp", "1.3.6.1.4.1.9.1", "scalar")])]
    _write(tmp_path, "resources/definitions/os_detection/acmeos.yaml", "os: acmeos\nmib_dir: acme2\n")
    _write(tmp_path, "resources/definitions/os_discovery/acmeos.yaml", "oid: ACME-MIB::acmeTemp.0\nmib: ACME-MIB\n")
    _write(tmp_path, "LibreNMS/OS/Other.php", "<?php SnmpQuery::mibDir('acme')->get('.1.3.6.1.4.1.9.1.0');")
    u = collect_usage(tmp_path, mods)
    assert u.by_ref == {"acme2/ACME-MIB"} and u.by_name == {"acme2/ACME-MIB"}
    assert u.by_oid == {"acme/ACME-MIB"}  # the PHP file names folder acme


def test_bare_object_names_count_when_one_mib_defines_them(tmp_path):
    mods = _mods() + [Module("DUP-MIB", "d", "d/DUP-MIB", "pysmi", objects=[Obj("acmeIfName", "1.3.6.1.4.1.8.1", "column")])]
    _write(tmp_path, "resources/definitions/os_discovery/acmeos.yaml",
           "oid: acmeTemp\ndescr: 'Port {{ acmeIfName }}'\nvalue: status\n")
    _write(tmp_path, "includes/fan.inc.php", "<?php snmp_get($device, 'acmeFan.0'); $x = 'acmeTable';")
    u = collect_usage(tmp_path, mods)
    # acmeIfName is defined by two MIBs (ambiguous); "status" is not camelCase
    assert u.objects == {"acme/ACME-MIB": {"acmeTemp", "acmeTable"}, "other/ACME-MIB": {"acmeFan"}}
    assert u.by_object == {"acme/ACME-MIB", "other/ACME-MIB"}


def test_mib_dir_alone_does_not_count_a_mib_but_settles_ambiguous_names(tmp_path):
    mods = _mods() + [Module("DUP-MIB", "d", "d/DUP-MIB", "pysmi", objects=[Obj("acmeIfName", "1.3.6.1.4.1.8.1", "column")])]
    _write(tmp_path, "resources/definitions/os_detection/dos.yaml", "os: dos\nmib_dir: d\n")
    _write(tmp_path, "resources/definitions/os_discovery/dos.yaml", "oid: acmeIfName\n")
    u = collect_usage(tmp_path, mods)
    assert u.modules == {"d/DUP-MIB"}  # nothing else in folder d (or anywhere) is counted

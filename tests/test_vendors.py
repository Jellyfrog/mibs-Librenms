from mibsite.model import Module, Obj
from mibsite.vendors import parse_enterprise_numbers, classify, slugify, module_root_oid

IANA = """PRIVATE ENTERPRISE NUMBERS

Decimal
| Organization
| | Contact
| | | Email
| | | |
0
  Reserved
    Internet Assigned Numbers Authority
      iana&iana.org
9
  ciscoSystems
    Dave Jones
      davej&cisco.com
2636
  Juniper Networks, Inc.
    Juniper
      x&juniper.net
"""


def test_parse():
    e = parse_enterprise_numbers(IANA)
    assert e[9] == "ciscoSystems" and e[2636] == "Juniper Networks, Inc." and e[0] == "Reserved"


def _m(dir, objs, name="X-MIB"):
    return Module(name, dir, f"{dir}/{name}", "pysmi", objects=objs)


def test_classify():
    e = parse_enterprise_numbers(IANA)
    assert classify(_m("juniper/junos", [Obj("r", "1.3.6.1.4.1.2636.3", "identity")]), e) == "Juniper Networks, Inc."
    assert classify(_m("_root", [Obj("ifMIB", "1.3.6.1.2.1.31", "identity")]), e) == "Standards (IETF)"
    assert classify(_m("_root", [Obj("lldp", "1.0.8802.1.1.2", "identity")]), e) == "Standards (IEEE)"
    assert classify(_m("hp", []), e) == "Hp"
    assert classify(_m("_root", []), e) == "Other"
    assert classify(_m("_external", []), e) == "External"
    assert classify(_m("acme", [Obj("r", "1.3.6.1.4.1.424242", "node")]), e) == "Acme"


def test_root_oid_prefers_identity():
    m = _m("x", [Obj("a", "1.3.6.1.4.1.9.9", "node"), Obj("id", "1.3.6.1.4.1.9.9.1", "identity")])
    assert module_root_oid(m) == "1.3.6.1.4.1.9.9.1"


def test_slugify():
    assert slugify("Juniper Networks, Inc.") == "juniper-networks-inc"
    assert slugify("Standards (IETF)") == "standards-ietf"

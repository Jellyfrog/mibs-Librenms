from __future__ import annotations

from dataclasses import asdict, dataclass, field

ROOT_DIR = "_root"  # modules in LibreNMS's top-level mibs/ folder
EXTERNAL_DIR = "_external"  # public MIBs vendored in extra-mibs/


@dataclass
class Obj:
    name: str
    oid: str | None
    kind: str
    syntax: str | None = None
    access: str | None = None
    status: str | None = None
    units: str | None = None
    description: str | None = None
    indexes: list[str] = field(default_factory=list)
    augments: str | None = None
    enums: dict[str, int] | None = None
    objects: list[str] = field(default_factory=list)
    parent_ref: tuple[str, int] | None = None
    defined_twice: bool = False  # the MIB assigns this name more than once (different OIDs)


@dataclass
class TextualConvention:
    name: str
    syntax: str | None = None
    display_hint: str | None = None
    status: str | None = None
    description: str | None = None
    enums: dict[str, int] | None = None


# metaswitch/METASWITCH-MIB (92k objects) would otherwise be a 52 MB page no browser opens well.
MAX_PAGE_OBJECTS = 50_000


@dataclass
class Module:
    name: str
    dir: str
    file: str
    tier: str
    errors: list[str] = field(default_factory=list)
    imports: dict[str, list[str]] = field(default_factory=dict)
    identity: dict | None = None
    objects: list[Obj] = field(default_factory=list)
    tcs: list[TextualConvention] = field(default_factory=list)

    @property
    def shows_objects(self) -> bool:
        """False for MIBs too large to show object by object: their page has no OID tree or object lists,
        and search links only to the MIB (object #anchors would not exist)."""
        return len(self.objects) <= MAX_PAGE_OBJECTS

    @property
    def id(self) -> str:
        return f"{self.dir}/{self.name}"

    @property
    def label(self) -> str:
        """How the site names this module: IF-MIB for LibreNMS's top-level mibs/, else cisco/CISCO-SMI."""
        return self.name if self.dir == ROOT_DIR else self.id

    @property
    def url(self) -> str:
        return f"/mib/{self.label}/"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        d = dict(d)
        objs = []
        for o in d.pop("objects"):
            o = dict(o)
            if o.get("parent_ref") is not None:
                o["parent_ref"] = tuple(o["parent_ref"])
            objs.append(Obj(**o))
        tcs = [TextualConvention(**t) for t in d.pop("tcs")]
        return cls(objects=objs, tcs=tcs, **d)

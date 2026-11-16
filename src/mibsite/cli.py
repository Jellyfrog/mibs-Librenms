from __future__ import annotations

import argparse
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="mibsite", description="Static MIB browser generator for LibreNMS")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the static site")
    b.add_argument("--librenms", type=Path, default=Path(".cache/librenms"))
    b.add_argument("--out", type=Path, default=Path("site"))
    b.add_argument("--base-url", default="https://mibs.librenms.org")
    b.add_argument("--jobs", type=int, default=os.cpu_count())
    b.add_argument("--only", help="glob on MIB path relative to mibs/, e.g. 'cisco/*'")
    b.add_argument("--extra", type=Path, default=Path("extra-mibs"))
    b.add_argument("--cache", type=Path, default=Path(".cache"))
    f = sub.add_parser("fetch-extra", help="download public MIBs that LibreNMS MIBs import but do not ship")
    f.add_argument("--librenms", type=Path, default=Path(".cache/librenms"))
    f.add_argument("--extra", type=Path, default=Path("extra-mibs"))
    args = p.parse_args(argv)
    if args.cmd == "build":
        from .build import build
        build(args.librenms, args.out, args.base_url, args.jobs, args.only, args.extra, args.cache)
    else:
        from .extra import fetch_extra
        fetch_extra(args.librenms / "mibs", args.extra)


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Fetch/update LibreNMS and build the site into ./site. Extra args go to `mibsite build`.
set -euo pipefail
cd "$(dirname "$0")/.."
scripts/fetch-librenms.sh .cache/librenms
PATH="$(scripts/install-net-snmp.sh):$PATH"  # net-snmp 5.10 (much faster on huge MIBs than 5.9)
export PATH
uv run mibsite build --librenms .cache/librenms --out site "$@"
echo "Preview: python3 -m http.server -d site 8000"

#!/usr/bin/env bash
# Sparse-clone (or update) LibreNMS with only what mibsite reads: mibs/ (the MIBs), tests/snmpsim/
# (snmprec device recordings, the source of the example values) and the OS definitions and PHP code
# (which MIB objects LibreNMS uses; see usage.py).
set -euo pipefail
dest="${1:-.cache/librenms}"
if [ -d "$dest/.git" ]; then
  git -C "$dest" fetch --quiet --depth 1 origin master
  git -C "$dest" reset --quiet --hard FETCH_HEAD
else
  git clone --quiet --depth 1 --filter=blob:none --sparse https://github.com/librenms/librenms.git "$dest"
fi
git -C "$dest" sparse-checkout set --no-cone "/mibs/" "/tests/snmpsim/" "/resources/definitions/" "/LibreNMS/" \
  "/includes/" "/app/"
git -C "$dest" rev-parse HEAD

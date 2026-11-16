#!/usr/bin/env bash
# Build net-snmp's command-line tools (snmptranslate) from a release tag into .cache/net-snmp/<version>.
# Prints the bin directory; does nothing if that version is already built.
set -euo pipefail
version="${NET_SNMP_VERSION:-5.10.rc1}"
prefix="$(pwd)/.cache/net-snmp/$version"
if [ -x "$prefix/bin/snmptranslate" ]; then
  echo "$prefix/bin"
  exit 0
fi
src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
curl -sfL "https://github.com/net-snmp/net-snmp/archive/refs/tags/v$version.tar.gz" | tar -xz -C "$src" --strip-components=1
cd "$src"
./configure --quiet --prefix="$prefix" --with-defaults --disable-agent --disable-embedded-perl \
  --without-perl-modules --disable-scripts --disable-manuals --without-openssl >/dev/null
make -s -j"$(nproc)" >/dev/null 2>&1
make -s install >/dev/null 2>&1
echo "$prefix/bin"

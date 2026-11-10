#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source "$root/scripts/libretto/toolchain.env"
archive="$root/_downloads/ow-$WATCOM_RELEASE.tar.xz"
destination=${LIBRETTO_WATCOM:-"$root/_watcom"}

for tool in curl sha256sum tar xz; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done

mkdir -p "$root/_downloads"
if [[ ! -f "$archive" ]]; then
    curl --fail --location --retry 3 \
        "https://github.com/open-watcom/open-watcom-v2/releases/download/$WATCOM_RELEASE/ow-snapshot.tar.xz" \
        --output "$archive.partial"
    mv -- "$archive.partial" "$archive"
fi
printf '%s  %s\n' "$WATCOM_SHA256" "$archive" | sha256sum --check --status

# Refuse to mix compiler versions in an existing installation.
if [[ -d "$destination" && -n "$(ls -A -- "$destination")" ]]; then
    if [[ ! -f "$destination/.libretto-toolchain" ]] || \
       [[ "$(cat "$destination/.libretto-toolchain")" != "$WATCOM_SHA256" ]]; then
        echo "Use an empty LIBRETTO_WATCOM directory for the pinned compiler." >&2
        exit 1
    fi
else
    mkdir -p "$destination"
    tar -xJf "$archive" -C "$destination"
    printf '%s\n' "$WATCOM_SHA256" > "$destination/.libretto-toolchain"
fi
test -x "$destination/binl64/wmake"
printf 'Compiler installed in %s\n' "$destination"

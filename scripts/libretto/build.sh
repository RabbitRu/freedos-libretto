#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
fat=${1:-32}
case "$fat" in
    16|32) ;;
    *) echo 'Usage: build.sh [16|32]' >&2; exit 2 ;;
esac

export WATCOM=${LIBRETTO_WATCOM:-"$root/_watcom"}
export PATH="$WATCOM/binl64:$PATH"
for tool in make wmake wcc wcl386 wlink wlib nasm qemu-system-i386 mtype python3; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
if [[ ! -f country/country.asm ]]; then
    echo 'Run git submodule update --init country before building.' >&2
    exit 1
fi
if [[ -f config.mak ]]; then
    echo 'Move config.mak aside: this build uses explicit, comparable options.' >&2
    exit 1
fi

output="$root/_output/libretto-fat$fat"
mkdir -p "$output"
# Upstream makefiles do not track compiler options as prerequisites.
make clobber COMPILER=owlinux XCPU=386 XFAT="$fat" XUPX= RM='rm -f'
make all COMPILER=owlinux XCPU=386 XFAT="$fat" XUPX= RM='rm -f'
cp bin/kwc386"$fat".sys "$output/KERNEL.SYS"
cp bin/kwc386"$fat".map "$output/kernel.map"
cp bin/country.sys "$output/COUNTRY.SYS"

for ram in 20 32; do
    (
        cd test
        export LIBRETTO_RAM_MB=$ram
        export QEMU="$root/scripts/libretto/qemu-pentium.sh"
        ./test.sh "$output/KERNEL.SYS" "libretto-$ram" "libretto-boot-$ram" \
            "Pentium / $ram MiB / FAT$fat: "
        cp "libretto-$ram.img" "$output/boot-test-$ram.img"
    )
done

python3 - "$output" "$fat" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

output = Path(sys.argv[1])
kernel = (output / "KERNEL.SYS").read_bytes()
report = {
    "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip()),
    "compiler": "Open Watcom 2026-11-01-Build",
    "cpu_target": "386",
    "fat_support": "FAT12/16" + ("/32" if sys.argv[2] == "32" else ""),
    "upx": False,
    "kernel_file_bytes": len(kernel),
    "kernel_sha256": hashlib.sha256(kernel).hexdigest(),
    "boot_tests": {"qemu_pentium_20_mib": "pass", "qemu_pentium_32_mib": "pass"},
    "limitations": [
        "File size is not resident memory consumption.",
        "Both boot images use FAT12; FAT16/FAT32 filesystem I/O is not tested here.",
        "Boot test checks creating, writing and closing one file; game compatibility is not tested.",
        "QEMU is not a cycle-accurate Libretto benchmark."
    ],
}
(output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
PY

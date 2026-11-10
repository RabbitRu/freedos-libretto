#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
fat=32
cpu=${1:-486}
[[ $# -le 1 ]] || { echo 'Usage: build.sh [486|pentium-mmx]' >&2; exit 2; }
case "$cpu" in
    486) export LIBRETTO_TUNE=4 ;;
    pentium-mmx) export LIBRETTO_TUNE=5 ;;
    *) echo 'Usage: build.sh [486|pentium-mmx]' >&2; exit 2 ;;
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

output="$root/_output/libretto-$cpu-fat$fat"
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
        export LIBRETTO_CPU=$cpu
        export QEMU="$root/scripts/libretto/qemu-target.sh"
        ./test.sh "$output/KERNEL.SYS" "libretto-$ram" "libretto-boot-$ram" \
            "$cpu / $ram MiB / FAT$fat: "
        cp "libretto-$ram.img" "$output/boot-test-$ram.img"
    )
done

python3 - "$output" "$cpu" "$LIBRETTO_TUNE" <<'PY'
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
    "c_cpu_target": sys.argv[2],
    "compiler_cpu_option": "-" + sys.argv[3],
    "assembly_cpu_target": "386",
    "fat_support": "FAT12/16/32",
    "mmx_specific_routines": False,
    "upx": False,
    "kernel_file_bytes": len(kernel),
    "kernel_sha256": hashlib.sha256(kernel).hexdigest(),
    "boot_tests": {"qemu_" + sys.argv[2] + "_20_mib": "pass", "qemu_" + sys.argv[2] + "_32_mib": "pass"},
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

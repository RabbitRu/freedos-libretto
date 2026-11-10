# FreeDOS for Libretto: starting point

This fork targets a small DOS gaming system on the Libretto, initially a
Pentium with 20 MiB RAM. A 32 MiB emulator configuration is also checked.
The kernel is built for 386+; no MMX requirement is introduced.

Upstream starting commit: `ca25e3b26695074f754e1baffdfb4fd1452a6dbc`
from [FDOS/kernel](https://github.com/FDOS/kernel).

## First milestone

Establish build and boot baselines before changing kernel behavior. The
`libretto` branch adds a separate GitHub Actions workflow and leaves upstream
kernel sources unchanged. Two existing build configurations are compared:

| Profile | CPU target | Filesystem support | Compression |
| --- | --- | --- | --- |
| Full | 386+ | FAT12, FAT16, FAT32 | None |
| Compact | 386+ | FAT12, FAT16 | None |

The compact profile uses an existing upstream option; it is not a new kernel
optimization. Choose the full profile if the intended disk uses FAT32.

Open Watcom is pinned to the official 2026-11-01 release and the download's
SHA-256 is verified. Distribution packages provide NASM, QEMU and mtools;
their exact versions are visible in the CI package installation log.
This establishes comparable builds, not a bit-for-bit reproducibility claim.

## Build on Linux

Install `make`, `curl`, `xz-utils`, `nasm`, `qemu-system-x86`, `mtools`, and
Python 3. Then, from a clean checkout:

```sh
git submodule update --init --recursive
bash scripts/libretto/bootstrap.sh
bash scripts/libretto/build.sh 32
bash scripts/libretto/build.sh 16
```

The build uses `_watcom/` by default; `LIBRETTO_WATCOM` can select a separate
compiler installation. A personal `config.mak` must be moved aside first.

Each build uses the upstream boot test on QEMU's Pentium model at 20 and
32 MiB. Successful boot and file creation/write/close are required. Outputs
go to `_output/libretto-fat16/` or `_output/libretto-fat32/` and include:

- `KERNEL.SYS`, linker map and `COUNTRY.SYS`;
- two FAT12 floppy images containing the upstream test program;
- `report.json` with kernel file size, checksum and test results.

The images run a test and shut down. They do **not** include a command shell
or an installer. No hard disk installation or formatting is performed.

## What remains to measure

Kernel file size does not establish the amount of conventional memory left
for games. The current tests do not establish FAT16/FAT32 disk correctness,
XMS/EMS compatibility, sound support, or compatibility with particular games.

Next steps are to collect resident/conventional memory measurements, add
file operation and game compatibility tests, and profile DOS file access.
Any assembly optimization should be isolated and compared against this
baseline. Timing on an actual Libretto is required for performance claims;
QEMU does not accurately model its CPU, disk or graphics timing.

The fork retains upstream's license; see `COPYING`.

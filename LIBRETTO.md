# FreeDOS for Libretto

This fork provides exactly two Libretto build profiles, both with FAT32
support. They retain the existing DOS APIs, calling conventions, packed
structures and 386-compatible kernel assembly.

Upstream starting commit: `ca25e3b26695074f754e1baffdfb4fd1452a6dbc`
from [FDOS/kernel](https://github.com/FDOS/kernel).

| Profile | C compiler target | Filesystem support | QEMU CPU |
| --- | --- | --- | --- |
| `486` | Open Watcom `-4` | FAT12, FAT16, FAT32 | `486` |
| `pentium-mmx` | Open Watcom `-5` | FAT12, FAT16, FAT32 | `pentium,mmx=on` |

The Pentium MMX profile uses the compiler's Pentium instruction selection
and timings. It does not yet contain new MMX-specific routines. Such routines
require separate correctness, x87-state preservation and performance tests.
See the official [Open Watcom C/C++ User's Guide](https://open-watcom.github.io/open-watcom-v2-wikidocs/cguide.html)
for processor selection options.

The profile is passed through `LIBRETTO_TUNE=4` or `5`; ordinary upstream
builds without this variable retain their existing settings. Both profiles
keep size optimization (`-os`) and disable UPX so binary sizes can be compared.

## Build on Linux

Install `make`, `curl`, `xz-utils`, `nasm`, `qemu-system-x86`, `mtools`, and
Python 3. Then, from a clean checkout:

```sh
git submodule update --init --recursive
bash scripts/libretto/bootstrap.sh
bash scripts/libretto/build.sh 486
bash scripts/libretto/build.sh pentium-mmx
```

Open Watcom is pinned to the official 2026-11-01 release, and its archive's
SHA-256 is verified before extraction. `_watcom/` is the default destination;
`LIBRETTO_WATCOM` can select a separate installation. A personal `config.mak`
must be moved aside first.

GitHub Actions builds both profiles. Each must boot and create/write/close
a file on its target CPU model with both 20 and 32 MiB of RAM. Outputs go to
`_output/libretto-486-fat32/` and `_output/libretto-pentium-mmx-fat32/`:

- `KERNEL.SYS`, linker map and `COUNTRY.SYS`;
- two FAT12 floppy images containing the upstream test program;
- `report.json` recording the CPU option, kernel size, checksum and results.

These are test images: they run a test and shut down. They contain neither
a command shell nor an installer and do not install or format a hard disk.

## Measurement limits

FAT32 is enabled in both kernels. The current boot test uses a FAT12 floppy;
it does not yet validate reads and writes on a FAT32 volume. Game compatibility,
XMS/EMS and sound support also require further tests.

Kernel file size does not measure resident memory or conventional memory
available to games. QEMU is not a cycle-accurate Libretto benchmark; speed
claims require measurements on the actual machine. Distribution packages
supply NASM, QEMU and mtools, with their versions visible in CI logs; this
is not a bit-for-bit reproducibility claim.

The fork retains upstream's license; see `COPYING`.

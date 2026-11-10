# FreeDOS for Libretto

Exactly two CPU profiles are built, both with FAT12/16/32 support:

| Profile | C compiler option | QEMU CPU |
| --- | --- | --- |
| 486 | Open Watcom -4 | 486 |
| pentium-mmx | Open Watcom -5 | pentium,mmx=on |

The profiles preserve DOS APIs, ABI, packed structures and 386-compatible
assembly. No MMX-specific kernel routines have been added. The starting kernel
was 72235 bytes and identical in both profiles. See OPTIMIZATION_PLAN.md and
MEASUREMENTS.md for the plan, completed validation and measured memory baseline.

## Packages

Each successful CI artifact contains:

- interactive-fat32.img.gz: a bootable MBR disk with a 64 MiB FAT32 volume,
  FreeCOM 0.86, HIMEMX 3.40 and JemmEX 5.86;
- dos-tools.zip: standalone MEMSTAT.COM, FSVERIFY.EXE and DOSBENCH.EXE;
- KERNEL.SYS, COUNTRY.SYS, linker map and original FAT12 test images;
- report.json, fat32-tests.json, runtime.json and benchmark CSV files;
- licenses and source archives for the external DOS components.

The disk has a boot menu: **0 Basic**, **1 XMS/HMA**, **2 XMS/EMS/UMB**.
The default is Basic. AUTOEXEC reports memory and enters the FreeCOM prompt.
No installer runs and no other disk is formatted.

To inspect it in QEMU, decompress the disk and attach only this image:

~~~sh
gzip -dk interactive-fat32.img.gz
qemu-system-i386 -cpu 486 -m 20 -drive file=interactive-fat32.img,format=raw,if=ide
# For the other package: -cpu pentium,mmx=on
~~~

Both CPU builds use the same shell, FILES=20, BUFFERS=20, LASTDRIVE=E and
STACKS=9,256. XMS allows FreeCOM to swap part of itself out of conventional
memory, and DOS=HIGH relocates DOS code into HMA. The EMS profile additionally
uses JemmEX and DOSDATA=UMB. These configuration effects are measured
separately from changes to kernel algorithms.

## Diagnostics on DOS hardware

Extract dos-tools.zip into a writable DOS directory, then run:

~~~bat
VER > VERSION.TXT
MEMSTAT > MEMORY.TXT
DOSBENCH 10 > BENCH.CSV
~~~

Record CPU model/clock, RAM, disk or adapter, DOS version, boot configuration
and cache state. Compare the same workloads/configuration on the control
kernel. DOSBENCH creates and removes a private LBBENCH directory; it refuses
to proceed if that directory exists. It measures 1 MiB writes including
flush, repeated 16 MiB reads, 1 MiB random reads, and creation/deletion of 100
small files. Times are raw BIOS ticks. Zero-duration or noisy measurements
require longer workloads; these are not FPS measurements.

MEMSTAT shrinks its own PSP block. Values describe memory **while the probe
runs under FreeCOM**; probe size is reported separately. It records the
original UMB link state, temporarily links UMBs to enumerate them and restores
the original state. An unlinked chain does not mean there are no UMBs.
XMS/EMS free capacity is queried through the corresponding driver.

FSVERIFY requires a fresh FSWORK directory. It creates test files and leaves
FRAGA.BIN and FRAGB.BIN for independent verification. Do not use an existing
directory with the same name for unrelated data.

## Validation

For each CPU, CI runs the original FAT12 boot test at 20 and 32 MiB and the
FAT32 disk with Basic/XMS/EMS configurations at both RAM sizes. It checks
MEMSTAT, FSVERIFY and one DOSBENCH run, then shuts down via APM. A separate
test boots the actual interactive menu image and sends a command through the
emulated keyboard, requiring a result file and successful shutdown.

FSVERIFY covers create/read/write/append/seek/truncate/rename/delete,
mkdir/chdir/rmdir, sizes around 512 bytes, 4 KiB and 64 KiB, and two interleaved
128 KiB files. Host code independently compares their bytes, walks FAT chains
to verify fragmentation and runs fsck.fat -n on the volume. Partial artifacts
from failed jobs retain fat32_validation=pending; use successful runs.

Game compatibility, DOS extenders, full-volume failures and injected I/O errors
remain separate work items. QEMU verifies correctness; emulator benchmark
timings do not establish performance on actual Libretto hardware.

## Rebuild

Linux dependencies: make, curl, xz-utils, NASM, QEMU system x86, mtools,
dosfstools, Python 3. The compiler snapshot and runtime binary archives have
pinned SHA-256 values. Distribution package versions appear in CI logs.

~~~sh
git submodule update --init --recursive
bash scripts/libretto/bootstrap.sh
bash scripts/libretto/build.sh 486
bash scripts/libretto/build.sh pentium-mmx
~~~

The compiler installs in _watcom/; LIBRETTO_WATCOM overrides it. Move a personal
config.mak aside for comparable builds. Outputs are under
_output/libretto-486-fat32/ and _output/libretto-pentium-mmx-fat32/.
Kernel license: COPYING. Runtime versions and hashes: runtime.json.

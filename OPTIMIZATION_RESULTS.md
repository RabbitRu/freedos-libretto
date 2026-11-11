# First FAT32 lookup optimization

Tested source: c6161b4672f5af8bc83873ef42402c0634d17397.
[Complete CI run](https://github.com/RabbitRu/freedos-libretto/actions/runs/42838513808).
Control: 4e438f419652fef6975b8e7bb0e7ab6835de8ad0, rebuilt with the same pinned
Open Watcom snapshot and target settings.

## Diagnosis and change

A separate diagnostic kernel found 1,398,367 FAT-chain steps and 2,796,734 FAT
reads for 2,048 random 512-byte reads of a 1 MiB file. All FAT reads hit the
buffer cache; there were 2,048 disk transfer calls. Operation counts were
identical before and after the patch on both CPU models.

Disassembly showed two software unsigned-32-bit divisions per FAT entry
lookup: remainder and quotient. For 128 entries per sector, the patch uses
a 127 mask and division by 128 through a right shift. The Watcom 386+ path
inlines SHRD AX,DX,7 and SHR DX,7, preserving the full 32-bit result.
Other compiler/CPU combinations use C; other divisors retain general
arithmetic. FAT validation, buffer replacement, disk requests and DOS structure
layouts are unchanged. Release builds add no MMX instructions or resident counters.

## Release measurements

QEMU 8.2.2, one vCPU/TCG thread, fixed icount, 20 MiB RAM, XMS/HMA,
64 MiB FAT32, 512-byte sectors/clusters, BUFFERS=20. Ten samples per workload,
kernel and CPU, fresh disks, ABBA boot order. The table is the median paired
change in executed instructions outside 0xA0000..0xFFFFF (ROM/VGA). Negative
values mean fewer instructions. This counter includes DOS and the benchmark.

| Workload | 486 change | Pentium MMX change |
| --- | ---: | ---: |
| Flushed 1 MiB write | -4.6486% | -4.6486% |
| Repeated 16 MiB read | -4.2331% | -4.2331% |
| Random 1 MiB read | -7.1671% | -7.1671% |
| 100 small files | -0.3793% | -0.3790% |


The earlier identical-kernel calibration measured at most 0.00005952% absolute
median paired change. Raw samples and ranges are retained in
comparison/comparison.json, CSV and CI logs. Counts including BIOS polling
are noisier.

KERNEL.SYS: 72,235 -> 72,283 bytes (+48). Both profiles produce the same binary.
Control SHA-256: 0687fd5f22fc984c95debf10294ca3a2f15705e7b4c0c0fabf4a659ec4511a74.
Candidate SHA-256: a9ed8607cb5657828ee4c0259e8bafda19e581b3e914b2f87e19a1a1e0fc9d25.
The final CI source checkout was clean.

Free conventional memory while MEMSTAT runs under FreeCOM:

| Profile | Control bytes | Candidate bytes | Change |
| --- | ---: | ---: | ---: |
| Basic | 510400 | 510352 | -48 |
| XMS/HMA | 631280 | 631280 | 0 |
| EMS/UMB | 637552 | 637552 | 0 |

## Correctness and scope

- 12 FAT32 runs across both CPUs, Basic/XMS/EMS and 20/32 MiB. Each checks
  12 boundary sizes, 1,288,568 assertions, two independently verified
  128 KiB files with 256 fragments each, and fsck.fat.
- Four original FAT12 tests and two interactive keyboard/prompt tests.
- 14 new edge-case boots across both CPUs: FAT16/FAT32 full-volume short
  writes, exact length/data/EOF, allocation after freeing space, persistent
  block read/write EIO delivered to DOS, unchanged fault-target data checked
  independently after shutdown, and clean fsck.fat. The FAT32 high-cluster
  fixture checks random forward/backward and cross-sector reads of a file
  starting above cluster 65535.
- All seven edge cases also passed locally with the lookup change present and
  removed, using QEMU 10.0.13. Local runs are correctness evidence, not the
  source of the instruction comparison.

This is a reduction in executed instructions in these workloads, not a
measured native CPU speedup, game FPS gain or full compatibility claim.
QEMU does not model the actual CPU caches, bus or instruction latency.
Larger clusters and different cache conditions may change the benefit.
Physical Libretto timing is a later confirmation step.

The next candidate is reducing repeated FAT-chain walks on backward/random
seeks. Any checkpoint/cache needs explicit invalidation for truncate,
extension, handle sharing and media changes; it is outside this patch.

Raw snapshots: [486](measurements/2026-11-10/486.json) and
[Pentium MMX](measurements/2026-11-10/pentium-mmx.json). The build-stage
report.json precedes the edge-test step; edge-tests/results.json records the
completed failure-path checks and supersedes that earlier snapshot's scope.

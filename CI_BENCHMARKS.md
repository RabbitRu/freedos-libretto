# Early optimization comparisons in CI

The existing GitHub Actions workflow builds both FAT32 CPU profiles, runs
correctness checks, and compares each candidate with the fixed control commit
4e438f419652fef6975b8e7bb0e7ab6835de8ad0. Physical Libretto measurements are a
later validation step; they do not block early kernel work.

The control is rebuilt with the same compiler, FAT32/CPU settings and date.
Both variants use the same DOSBENCH, runtime, FAT32 geometry, XMS/HMA and
20 MiB RAM. Order: control/candidate/candidate/control. Each boot starts with
a fresh disk and runs five repetitions: ten samples per scenario and variant.
Kernels, input hashes, raw CSV, JSON and Markdown reports are retained under
comparison/ in the normal artifact.

A QEMU 8.2 TCG plugin counts instructions between unique, harmless MOV EAX
markers around each measured region. It records all guest instructions and
a second address-window count excluding 0xA0000..0xFFFFF. This second metric
is not kernel-only. The runner enforces one vCPU and one TCG thread.
The vendored plugin API header is from official QEMU v8.2.2.

Fixed icount timing reduces dependence on runner scheduling. These counts
are NOT cycle-accurate 486/Pentium timings: QEMU does not model their actual
instruction latency, caches or bus. BIOS ticks use an artificial clock.
Host wall time is diagnostic only.

Primary QEMU documentation:
- https://github.com/qemu/qemu/blob/v8.2.2/docs/devel/tcg-icount.rst
- https://github.com/qemu/qemu/blob/v8.2.2/docs/devel/tcg-plugins.rst

If kernels are byte-identical, input images must also be identical. This is
calibration, not evidence of an optimization. A median paired non-ROM count
difference over 1% labels calibration noisy; all raw samples and ranges are
kept. Subsequent patches must improve beyond the observed noise, retain
correctness, and report code/data and memory costs. Native hardware timing
can confirm the actual speedup later.


## Diagnostic counters and filesystem edge cases

Separate profile jobs compile with LIBRETTO_PROFILE. Unique instruction
markers count map calls, chain steps, backward seeks, FAT reads/writes,
buffer probes/hits/misses and disk transfer calls inside each workload.
The QEMU plugin holds the counters. Release builds emit no diagnostic
markers, carry no counters and retain the DOS structure layouts/ABI.
Diagnostic instruction totals must not be compared with release totals.

Normal build jobs also boot FAT16 and FAT32 fixtures with almost-full
volumes and persistent QEMU blkdebug read/write EIO injection. Tests require
short-write length/data correctness, cleanup and successful allocation after
freeing space, failure delivery to the DOS application, unchanged fault-target
data and a clean independent fsck.fat. A FAT32 fixture places a file above
cluster 65535 and verifies random forward/backward, cross-sector reads.
The high-cluster fixture is checked independently on the host before boot.

Injection method: https://github.com/qemu/qemu/blob/v8.2.2/docs/devel/blkdebug.txt

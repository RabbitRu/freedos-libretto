# Validated backward FAT-seek checkpoints

The complete final CI matrix passed:
[run 42883124425](https://github.com/RabbitRu/freedos-libretto/actions/runs/42883124425).
Published kernel source: 83aa1e1d852ef28aba721acbf4f13a1737310691.
Tested PR merge: 4a24bdaa80aa2523f1330e88fbdd6154b357a747. Its tree
47bd29695287db684f246c0440a174ac5a1a5ede matches the published source tree.
Control: 5f17969cd603eeef159f8706e63ee7631ecd5419, which already includes the
previous FAT32 division optimization.

## Instruction-count comparison

QEMU 8.2.2 (Ubuntu 8.2.2+ds-0ubuntu1.18), one vCPU/TCG thread, fixed icount
shift=3, 20 MiB, XMS/HMA, 64 MiB FAT32, 512-byte sectors/clusters. Ten samples
per workload, kernel and CPU, fresh disks, ABBA order. Values are median
paired changes in executed guest instructions outside ROM/VGA addresses
0xA0000..0xFFFFF. This metric includes DOS and the benchmark.

| Workload | 486 | Pentium MMX |
| --- | ---: | ---: |
| Flushed 1 MiB write | -0.0481% | -0.0481% |
| Repeated 16 MiB read | -0.3564% | -0.3565% |
| Random 1 MiB read | -37.3610% | -37.3610% |
| 100 small files | -0.2419% | -0.2419% |

All four measured workloads use fewer instructions. The principal improvement
is random access; the smaller changes are instruction-count results, not
claims of matching percentage gains on hardware. QEMU does not model native
486/Pentium caches, bus bandwidth or instruction latency. Different cluster
sizes and workloads can change the benefit. Game FPS and native Libretto
speed remain unmeasured.

The [first checkpoint version](measurements/2026-11-11/checkpoints-v1) passed
its full matrix too, but added +1.75% instructions to writes and +1.04% to
sequential reads. Its result led to the write-only inline invalidation change.
The final comparison above supersedes those overheads.

## Size and conventional memory

Both CPU profiles produce the same 72,763-byte KERNEL.SYS, versus the accepted
72,283-byte control (+480 bytes). Candidate SHA-256:
d2d2fcb037bcb1115777267e2f635f8743b6d5953628c78bd17e04385e890fd2.
Control SHA-256:
a9ed8607cb5657828ee4c0259e8bafda19e581b3e914b2f87e19a1a1e0fc9d25.

| Free conventional bytes while MEMSTAT runs | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| Basic | 510352 | 509872 | -480 |
| XMS/HMA | 631280 | 631200 | -80 |
| EMS/UMB | 637552 | 637472 | -80 |

The cache and its validity byte occupy 75 bytes of resident data. DOS
paragraph allocation costs 80 conventional bytes with HMA/UMB placement.
Basic also keeps the added code low. Largest free blocks are 509728, 631056
and 637328 bytes respectively while the 3440-byte probe runs under FreeCOM.
Both CPUs and both tested RAM sizes produced these same memory values.

## Operation counts

Both final diagnostic profiles recorded 873,173 chain steps and 1,746,346 FAT
reads during 2,048 random 512-byte reads of a 1 MiB file. The previous
validated control recorded 1,398,367 steps and 2,796,734 FAT reads: a 37.56%
reduction. Disk calls remain 2,048; 909 backward reads use checkpoints.
Bounded mapper re-entry adds map-call events without adding chain steps.
Diagnostic instruction totals are separate from release performance data.

## Correctness

All four final CI jobs passed, for 74 DOS boots:

- Four original FAT12 boot/write checks at 20/32 MiB.
- Twelve FAT32 runs across both CPUs, Basic/XMS/EMS and 20/32 MiB. Each checks
  1,288,568 guest assertions, independent bytes, 256-fragment file chains and
  a clean fsck.fat result.
- Two tests typing a command at the actual interactive prompt.
- Fourteen FAT16/FAT32 edge runs: full disks, short writes, allocation after
  freeing space, persistent read/write EIO and physical FAT32 clusters above
  65535, with independent data and filesystem checks.
- Thirty-two chain boots on control and candidate for both CPUs: independent
  read handles, duplicated handles sharing a cursor, truncation/regrowth,
  deletion/recreation, switching files, absolute FAT32 rewrites and actual
  floppy replacement. Replacement media preserve geometry, first cluster
  and file length while reversing the remaining chain and changing data.
- Eight paired benchmark boots and two diagnostic boots.

Earlier local negative controls deliberately disabled invalidation and made
both raw-FAT and floppy-change tests detect incorrect data. Their temporary
logs were lost during a runtime restart. The two successful CI matrices and
raw artifacts retained here supersede the interrupted local positive run.
SHARE-mediated mutation through distinct SFTs, games and DOS extenders remain
untested; those are compatibility follow-ups.

## Implementation

Eight checkpoints retain successfully reached relative/physical cluster pairs
for one file chain, keyed by DPB and first cluster. Backward nonzero file reads
choose the nearest saved position at/before their target. Switching files
replaces the checkpoints. Directories and zero-offset rewinds keep their
existing path. A helper re-enters the normal forward mapper at most once,
retaining all existing FAT validation. Failed mappings are not cached.
SFT, fnode and public DOS layouts are unchanged.

A separate one-byte validity flag is cleared inline immediately before the
FAT12/16/32 mutation paths. Existing read-return branches bypass that store,
so reads do not pay for another read/write decision or an invalidator call.
Failures before a FAT entry changes leave the unchanged chain cache coherent.
Raw write attempts, media/buffer invalidation and block IOCTLs still discard
all checkpoints conservatively. External code bypassing DOS must honor its
existing buffer-coherence contract.

Exactly two profiles remain: 486 (-4) and Pentium MMX (-5), both FAT12/16/32
with 386 assembly and the pinned Open Watcom snapshot. No MMX routines are
added. Reproduction and local deadline overrides: [CI_BENCHMARKS.md](CI_BENCHMARKS.md)
and [LIBRETTO.md](LIBRETTO.md).

## Deliverables and raw evidence

- [486 package](https://github.com/RabbitRu/freedos-libretto/actions/runs/42883124425/artifacts/13795178495)
- [Pentium MMX package](https://github.com/RabbitRu/freedos-libretto/actions/runs/42883124425/artifacts/13795841462)
- [Final JSON/CSV, runtime and kernel hashes, artifact digests](measurements/2026-11-11/checkpoints-v2)
- [Previous checkpoint experiment](measurements/2026-11-11/checkpoints-v1)

Each CPU package includes the interactive FAT32 image, standalone DOS tools,
control/candidate comparison kernels, test results, licenses and runtime
sources. Build report scope precedes edge/chain testing; completed results of
those later steps are recorded separately in each raw snapshot.

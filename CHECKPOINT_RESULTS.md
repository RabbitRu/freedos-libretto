# Backward FAT-seek checkpoints

The first checkpoint implementation passed the complete CI matrix:
[run 42879726816](https://github.com/RabbitRu/freedos-libretto/actions/runs/42879726816).
Published source: 9ac3bfa5773a20a636746327d8c357ce131df0a1.
Tested PR merge: 75d13febc3605e21bf58d7a9bcaef7855868cf4d; its source tree
matches the published branch. Control: 5f17969cd603eeef159f8706e63ee7631ecd5419,
including the earlier FAT32 division optimization.

A follow-up moves invalidation out of FAT reads and uses an inline validity
byte. Its fresh validation is pending; the following numbers belong to the
first validated checkpoint implementation.

## Measured instruction counts

QEMU 8.2.2, one vCPU/TCG thread, fixed icount shift=3, 20 MiB, XMS/HMA,
64 MiB FAT32 volume, 512-byte sectors/clusters. Ten samples per workload,
kernel and CPU, fresh disks and control/candidate/candidate/control order.
Values are median paired changes in guest instructions outside ROM/VGA
addresses 0xA0000..0xFFFFF, including DOS and the benchmark.

| Workload | 486 | Pentium MMX |
| --- | ---: | ---: |
| Flushed 1 MiB write | +1.7482% | +1.7478% |
| Repeated 16 MiB read | +1.0394% | +1.0394% |
| Random 1 MiB read | -35.8392% | -35.8392% |
| 100 small files | -0.1188% | -0.1188% |

The random-read win is accompanied by roughly 1–2% more instructions in
sequential I/O. The follow-up specifically addresses that overhead rather
than treating the checkpoint patch as an unconditional speedup.
These counts are not native CPU cycles, Libretto timings or game FPS.
Different cluster sizes and workloads may change the benefit.

## Size, memory and operation counts

Both CPU profiles produce the same 72,747-byte kernel, versus 72,283 bytes
for control (+464 bytes). Candidate SHA-256:
fed9fc7ef23540d16358b38790c68f5483ddeb393c5fb0f1514a20d50bc16d2f.

| Conventional bytes while MEMSTAT runs | Control | Checkpoints | Change |
| --- | ---: | ---: | ---: |
| Basic | 510352 | 509888 | -464 |
| XMS/HMA | 631280 | 631200 | -80 |
| EMS/UMB | 637552 | 637472 | -80 |

The validated cache has 74 bytes of resident data. Both CPU/RAM variants
report the same conventional-memory values. In random access, chain steps
fall from 1,398,367 to 873,173 (37.56%), and FAT reads from 2,796,734 to
1,746,346. Disk calls remain 2,048. There are 909 checkpoint hits. Bounded
mapper re-entry adds map-call events without adding FAT-chain steps.

Raw JSON, CSV, kernel hashes, runtime hashes and successful artifact links:
[checkpoints-v1](measurements/2026-11-11/checkpoints-v1).
Build report scope precedes the separate edge and chain steps; their
completed results are included separately in each raw snapshot.

## Correctness

All four CI jobs passed, for a total of 74 DOS boots:

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
  floppy replacement. Replacement media keep geometry, first cluster and
  file length while reversing the remaining chain and changing contents.
- Eight paired benchmark boots and two diagnostic boots.

Earlier local negative controls deliberately disabled invalidation and made
both raw-FAT and floppy-change tests detect incorrect data. Their temporary
logs were lost during a runtime restart; the completed CI above supersedes
the interrupted local positive/comparison run.
SHARE-mediated mutation through distinct SFTs, games and DOS extenders
remain untested.

## Implementation and follow-up

Eight checkpoints retain successfully reached relative/physical cluster pairs
for one file chain, keyed by DPB and first cluster. Backward nonzero file reads
choose the nearest saved position at/before their target. Switching files
replaces the checkpoints. Directories and zero-offset rewinds keep their
existing path. A helper re-enters the normal forward mapper at most once,
retaining all existing FAT validation. Failed mappings are not cached.
SFT, fnode and public DOS layouts are unchanged.

FAT entry changes, buffer/media invalidation, DOS absolute write attempts and
block IOCTLs discard the cache. External code bypassing DOS must honor its
existing buffer-coherence contract.

The follow-up clears a separate one-byte validity flag directly before the
three FAT12/16/32 mutation paths. The existing read-return branches bypass
that store. This removes the extra read/write decision from every FAT lookup
and avoids a register-clobbering invalidator call. Failures before any FAT
entry changes leave the unchanged chain cache coherent. Absolute write
attempts, media invalidation and block IOCTLs still invalidate conservatively.
Its cache-data footprint is 75 bytes; actual binary/memory and performance
costs will be recorded after its own full CI run.

Exactly two profiles remain: 486 (-4) and Pentium MMX (-5), both FAT12/16/32
with 386 assembly and the pinned Open Watcom snapshot. No MMX routines are
added. Reproduction and deadline overrides: [CI_BENCHMARKS.md](CI_BENCHMARKS.md)
and [LIBRETTO.md](LIBRETTO.md).

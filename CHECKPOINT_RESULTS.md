# Backward FAT-seek checkpoint patch

The implementation is complete and committed locally. GitHub publication and
the final CI run are blocked by automatic approval review, which requires
explicit approval of publication to the public RabbitRu/freedos-libretto fork.
No remote branch was changed by this attempt.

Tested kernel source: ce7f07d0cf06536b09893cc8b7edf713632994a2.
Comparison control: 5f17969cd603eeef159f8706e63ee7631ecd5419, including the
previous FAT32 division optimization.

## Implementation

Eight checkpoints retain successfully reached relative/physical cluster pairs
for one file chain, keyed by DPB and first cluster. Backward nonzero file reads
start from the nearest saved position at/before their target. Switching files
replaces the checkpoints. Directory walks and zero-offset rewinds follow the
existing mapper. SFT, fnode and other public DOS layouts are unchanged.

Checkpoint work is confined to the backward branch. A helper re-enters the
normal mapper once after moving at/before the target; that inner call cannot
enter the backward helper again. Existing FAT-chain validation stays in the
normal walker. Failed mappings do not create checkpoints.

FAT write attempts, buffer/media invalidation, DOS absolute write attempts and
block IOCTLs discard the cache. External programs bypassing DOS must continue
to honor the existing DOS buffer-coherence contract.

Both FAT12/16/32 profiles build with the pinned Open Watcom snapshot: 486 (-4)
and Pentium MMX (-5), retaining 386 assembly. Neither adds MMX instructions.

## Completed local checks and limitations

The final source was built from clean checkouts for both CPU profiles. During
this session the following final-source checks completed successfully:

- Four original FAT12 boot/write tests at 20/32 MiB.
- Twelve FAT32 runs across both CPUs, Basic/XMS/EMS and 20/32 MiB. Each checks
  1,288,568 guest assertions, independently verified bytes and fragmentation,
  and a clean fsck.fat result.
- Two tests typing a command at the actual interactive prompt.
- Fourteen FAT16/FAT32 edge runs: full disks, short writes, recovery after
  freeing clusters, persistent read/write errors and physical FAT32 cluster
  numbers above 65535.
- Two negative controls using final mapper code with invalidation deliberately
  disabled: both the absolute-FAT and actual-floppy-change tests detected
  incorrect data as required.

The full 32-case chain suite passed on the preceding checkpoint implementation.
Its repeat on the final refactored mapper, the final diagnostic matrix, and the
complete ten-sample ABBA comparison were still pending when the environment
restarted. Temporary logs/results from those final worktrees did not survive.
Those checks must be rerun in CI before treating this patch as validated.

The chain suite covers independent read handles, duplicated handles sharing a
cursor, truncation/regrowth, deletion/recreation, file switching, absolute FAT32
rewrites and an actual floppy swap. The replacement FAT12 medium preserves
geometry, first cluster and file length while reversing the remaining chain
and changing data. Final file bytes and filesystem structure are checked
independently after DOS exits. SHARE-mediated mutation through distinct SFTs
and game/DOS-extender compatibility remain untested.

## Size and preliminary measurements

Both final kernels are byte-identical, 72,747 bytes versus the 72,283-byte
control (+464 bytes). SHA-256:
5efa82e32708fb8a70e969d8dad0a1ea9d3a4ecc725b26fb30f6c6455153be79.

The cache contains 74 bytes of resident data. Measured conventional memory
cost under XMS/HMA and EMS/UMB is 80 bytes; Basic retains the added code low
and loses 464 bytes.

The first checkpoint version reduced random-read chain steps from 1,398,367
to 873,173 (37.56%) while retaining 2,048 disk calls. It added about 1–2%
executed instructions to sequential workloads; the final refactor moved
checkpoint work off the common path to reduce that cost.

Captured individual release samples of the final version indicate roughly
36% fewer non-ROM guest instructions on the synthetic random-read workload.
This is preliminary: the complete ten-sample paired report was interrupted,
and its raw files were lost. There is no final accepted speedup percentage.

Measurements use QEMU 8.2.2, fixed icount, 20 MiB, XMS/HMA and a 64 MiB FAT32
volume with 512-byte sectors/clusters. Counts include DOS and the benchmark,
excluding ROM/VGA addresses 0xA0000..0xFFFFF. They are not native CPU cycles,
Libretto timings or game FPS. Different cluster sizes may change the benefit.

## Reproduction and CI

The workflow already builds exactly the two requested CPU profiles. Its normal
build jobs run build.sh, edges.py, compare.py and chains.py; separate profile
jobs count FAT operations. compare.py rebuilds the accepted control using the
same compiler and CPU flags. Ten samples per workload/kernel/CPU are retained
with fresh disks and control/candidate/candidate/control order.

```sh
bash scripts/libretto/bootstrap.sh
bash scripts/libretto/build.sh 486
python3 scripts/libretto/edges.py 486
python3 scripts/libretto/compare.py 486
python3 scripts/libretto/chains.py 486
python3 scripts/libretto/profile.py 486
```

Use pentium-mmx for the other profile. Comparison requires QEMU 8.2 matching
the vendored plugin API. Functional checks also ran with QEMU 10.0.13.
LIBRETTO_TEST_TIMEOUT can raise local subprocess deadlines and
LIBRETTO_COMPARE_TIMEOUT overrides the 420-second comparison deadline.
Defaults in CI, guest workloads and sample counts remain unchanged.

A local patch containing the committed source changes is available at
_output/review/backward-seek-checkpoints.patch. It updates the libretto work
branch after publication; it does not merge into master.

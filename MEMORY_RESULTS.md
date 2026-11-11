# Validated memory copy/fill optimization

Final source: `bdb3e00f3858bc8cbb3e1c369c1ce4fa65c6a73f`.
Tested PR merge: `430f06d30ff89431775678c6646c07b63f3990c1`.
Both have tree `b15cfc0619635f0f4c73c17a2a83be03ad5377cf`.
Control: merged master `28dc3c7f0ce5f29440905bc54af37591f8db8b67`, including the accepted FAT32 lookup and seek checkpoints.

[Final CI run 42956883375](https://github.com/RabbitRu/freedos-libretto/actions/runs/42956883375) passed all four required jobs and 78 DOS boots. The optional compiler scout is skipped in ordinary PR runs; its separate completed results are in [COMPILER_RESULTS.md](COMPILER_RESULTS.md).

## Implementation

The four near/far copy/fill procedures in `kernel/asmsupt.asm` set up only their required arguments. Watcom calls use fixed Pascal exits (`RET 6/8/10`) instead of shifting arguments and the return address on the stack. The exit target is derived from current CS:IP, so the same object also works inside a standalone DOS test EXE whose code layout differs from the kernel.

Blocks of at least 128 bytes may use `REP MOVSD`/`REP STOSD`, with 16-bit SI/DI/CX and no address-size prefix. A byte/word prefix aligns destination stores; copy source loads can remain unaligned. Offset-plus-length carry selects the original word path, so no dword crosses offset FFFF. A conservative low-16-bit physical-distance check also retains the old word-copy propagation for close forward overlap and segment aliases. Short blocks retain word transfers.

The fill path saves/restores full EAX while building its four-byte pattern. The procedures preserve the Watcom register contract, clear DF, and retain their existing Pascal argument sizes. No resident data, MMX, x87 state or filesystem structure changes are introduced. Temporary extra stack use is at most eight bytes for the fill pattern and two for the copy guard; the CS:IP setup call is balanced before transfers.

## Filesystem instruction counts

QEMU 8.2.2 Ubuntu `8.2.2+ds-0ubuntu1.18`, one vCPU/TCG thread, `icount shift=3`, 20 MiB XMS/HMA, fresh FAT32 disks, ABBA order and ten samples per workload/kernel/CPU. Values are median paired changes outside ROM/VGA addresses 0xA0000..0xFFFFF; this is not a kernel-only counter.

| Workload | 486 | Pentium MMX |
| --- | ---: | ---: |
| Flushed 1 MiB write | -0.3388% | -0.3381% |
| Repeated 16 MiB read | -0.5922% | -0.5922% |
| Random 1 MiB read | -0.0285% | -0.0285% |
| 100 small files | -2.7530% | -2.7530% |

All four workloads use fewer instructions. These percentages are not native 486/Pentium timings or game FPS. Instruction scheduling, unaligned reads, caches and bus bandwidth require later hardware measurement.

The memory runner also compares the actual reference/candidate assembly in isolation, using three repetitions of 128 calls for each size/alignment case. Complete microbenchmark medians and samples are in the final artifacts. Its independent REP calibration measures `n+2` instructions for n=0,1,64,1024 with each of MOVSB/MOVSW/MOVSD. QEMU counts REP iterations: reducing iteration count alone must not be described as an equal native speedup.

## Size and memory

Both CPU profiles produce the same 73,035-byte KERNEL.SYS, versus 72,763 bytes on the control (+272 bytes). Candidate SHA-256:

`6bd2dea0faf2bd4636a75b66e6eec5571a217d1bd5ca992769c166c9164ca4f3`.

| Free conventional bytes while MEMSTAT runs | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| Basic | 509872 | 509600 | -272 |
| XMS/HMA | 631200 | 631200 | 0 |
| EMS/UMB | 637472 | 637472 | 0 |

Control Basic/EMS figures are the accepted master baseline in CHECKPOINT_RESULTS.md; the paired run re-measures XMS/HMA on both kernels.

The added code occupies HMA when DOS is loaded high. Basic keeps it low. No new resident data/cache allocation is needed. Both RAM sizes and both CPUs report the same conventional values; the probe itself occupies 3440 bytes. Largest free candidate blocks are 509456, 631056 and 637328 bytes respectively. File size is not a general measure of resident memory.

## Validation and evidence

For each CPU, both reference and candidate objects pass 1648 independent byte-oracle/ABI cases. They cover all four functions, short/tail lengths and counts up to 65535, all source/destination alignments modulo four, full destination guards, segment wrapping, overlapping copies and segment aliases. The wrapper enters with DF=1 and checks SP cleanup, DS/ES/FS/GS, BX/CX/DX/SI/DI/BP and the tested high GPR halves, including EAX.

The full matrix also passes FAT12 boots, FAT32 Basic/XMS/EMS at 20/32 MiB, the interactive prompt, FAT16/FAT32 full-disk recovery, high clusters, injected I/O errors, chain/handle/truncation cases, raw FAT rewrites, actual emulated floppy replacement, and diagnostic profiles. The twelve FAT32 runs each pass 1,288,568 guest assertions, independent file/chain validation and fsck.

Committed [summary, calibration and filesystem records](measurements/2026-11-11/memory-v4) identify the tested hashes and artifact digests. The complete per-run CSV, standalone memory benchmark output, kernels, maps and boot images are in the CI artifacts; those downloads have GitHub retention limits.

- [486 final package](https://github.com/RabbitRu/freedos-libretto/actions/runs/42956883375/artifacts/13827783513)
- [Pentium MMX final package](https://github.com/RabbitRu/freedos-libretto/actions/runs/42956883375/artifacts/13827274742)

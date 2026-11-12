# JFT and INSTALL correctness fixes

The changes fix two findings from the 12 November kernel review, plus an
overflow in the same JFT allocation calculation. Baseline:
`87e7c3a1dfdd03035008c811f76633f1160a8f4e`; implementation:
`055f21bee627a15aa43aa36dbbda01220cd0e2f4`.

## JFT allocation lifetime and size

INT 21h/AH=67h previously allocated another table on each increase without
releasing the superseded external table. For example, 20 → 40 → 80 → 160
left 160 bytes of old tables and MCB headers until process cleanup.

The replacement is allocated, initialized and published before the old block
is freed. Failure leaves the old pointer, count and handles unchanged.
Kernel-created tables carry an eight-byte `FDJFT` MCB name marker. Reclamation
also requires an offset-zero table, a normal/last MCB, the current PSP owner
and sufficient block capacity. Program-supplied tables remain the caller's
responsibility. Markers are bookkeeping in unprotected DOS memory, not a
security boundary; a program changing the marker can prevent reclamation.
No per-process tracking array or additional allocation header is introduced.

Count-only shrinking retains its previous behavior: the current table stays
referenced and allocated, and handles are not closed by this operation. A
later growth releases this table after copying its visible entries.

The paragraph calculation now widens before adding 15. Requests from 65521
to 65535 therefore allocate 4096 paragraphs rather than wrapping the
16-bit sum and requesting zero paragraphs.

## CONFIG.SYS INSTALL boundary

The ten-entry array is checked with `>=` before indexing. The combined limit
applies to INSTALL and INSTALLHIGH. The first ten commands remain available;
the eleventh is diagnosed and rejected.

## Regression evidence

Run after building a target kernel and preparing the pinned runtime:

```sh
python3 scripts/libretto/kernel_checks.py 486
python3 scripts/libretto/kernel_checks.py pentium-mmx
```

Each target boots six JFT cases (Basic/XMS/EMS at 20/32 MiB) and three INSTALL
cases (9/10/11 mixed commands). JFT checks cover allocation counts and sizes,
growth, shrink/regrow, new closed entries, open/duplicated handles, shared
file position through EXEC, child memory cleanup, ENOMEM, 65521/65535 sizes,
and custom table offsets/owners. INSTALL programs trace actual execution to
QEMU debugcon; checking only a successful boot would miss the original bug.

Locally, QEMU 7.2.22 passed all 18 candidate boots. The unmodified baseline
failed both negative controls: a second external JFT allocation remained,
and eleven INSTALL programs actually executed. These failures establish
that the regression tests distinguish the baseline from the fix.

[local-results.json](measurements/2026-11-12/kernel-fixes/local-results.json)
records kernel hashes, cases and negative-control results. Both locally
built target kernels are byte-identical at 73195 bytes, +160 bytes versus
the baseline. File size is not resident-memory consumption or native timing.

The new checks are also part of the existing Libretto CI, alongside the
filesystem, memory/ABI, performance-count and diagnostic checks.
[CI run 43151483354](https://github.com/RabbitRu/freedos-libretto/actions/runs/43151483354)
passed all four required jobs, including the 18 new regression boots.
It tested merge `c1ee3b70256c9c612139b05bb6acb2d45cd1b3a4`, whose tree
`86b8d27fa53190b34d2af2b551dbd127a1326891` matches the implementation commit.
The archived target kernels match the local binaries exactly; both ZIP
artifact SHA-256 digests were checked against GitHub's artifact metadata.
Job identities, artifacts, hashes and complete new regression results:
[ci-results.json](measurements/2026-11-12/kernel-fixes/ci-results.json).

Conventional bytes free while the existing MEMSTAT probe is loaded, identical
for both CPU profiles and 20/32 MiB configurations:

| Boot profile | Baseline | Fixed | Change |
| --- | ---: | ---: | ---: |
| Basic | 509600 | 509440 | -160 |
| XMS/HMA | 631200 | 631200 | 0 |
| EMS/UMB | 637472 | 637472 | 0 |

Baseline values are the accepted master results in MEMORY_RESULTS.md. These
startup values exclude any later JFT growth by the application; reclaimed
table memory depends on its actual sequence of AH=67h requests. The patch
is a correctness fix and makes no native-speed or FPS claim.

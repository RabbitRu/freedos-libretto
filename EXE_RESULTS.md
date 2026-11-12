# MZ relocation loading

Baseline: `1c43e901dc699dce0a0a89301fccb09eddb6096d`.
Initial measured implementation (superseded): `2351226bc66070ff8b0344e541a9825a1f6d3340`.

## Change and ownership

For unmanaged local files, the EXE loader reads up to eight four-byte relocation records
per DosRWSft call. For N entries this changes N calls to ceil(N/8), or 4096 to
512 in the largest benchmark. Physical disk reads do not fall by the same factor:
the previous implementation already used the sector cache.

The buffer aliases 32 aligned bytes of existing rename scratch at SDA+300h.
The reserved scratch region is 53 bytes below the usable critical-error stack;
no stack boundaries, SDA offsets or resident data sizes change. EXEC and rename
are mutually exclusive INT 21h services. Local file reads use fnode[0], while
the aliased second directory-match buffer is used by rename's fnode[1]. Valid
INT 24h handling cannot nest a rename. The persistent-I/O-failure regression
checks that a partial batch survives the real critical-error path.

This also leaves the shell filename and command tail in SecPathName intact.
A local array was rejected because the disk API stack is only 384 bytes.
The final loader keeps the baseline's 20-byte Watcom frame. It consumes the
relocation count in the already parsed header, which is dead after this phase,
and reads the overlay adjustment at the point of application. Neither the
32-byte buffer nor loop state grows the frame. A 24-byte-frame intermediate
passed ordinary tests but failed when real SHARE was installed and was rejected.

Remote SFTs and local SFTs managed by SHARE retain four-byte requests. A
range-lock check applies to the entire requested range, so batching can change
the prefix or conflict behavior. The fallback is selected from sft_shroff as
well as SFT_FSHARED. The real-SHARE negative control fails when this guard is
removed. Relocations are applied in original order,
including duplicate, aliased and byte-overlapping target words. A short local
read applies all complete records preceding EOF or an I/O error, preserving
the baseline's caller-visible partial OVERLAY result. Failed ordinary loads
still free their image and environment and return invalid data.

## Validation

The host harness compiles the actual relocation block from task.c with traced
SFT read stubs under AddressSanitizer. Its 867 cases check local/remote/SHARE request
sizes and counts, all short lengths through a 17-entry table, negative reads,
ordered byte results, failure cleanup, and counts up to 65535. It does not
exercise a network redirector or the real-mode ABI.

The DOS harness compares the loaded image byte by byte against an independent
byte-based relocation oracle. Fixtures cover 0/1/7/8/9 and further batch
boundaries, 16383/16384/16385, 32767/32768/65535 entries, sector and 64 KiB
boundaries, duplicate/alias/overlapping targets, and all 0–9 complete records
followed by 0–3 bytes of a truncated table. Tables in short-file fixtures sit
after the declared image so that the image read remains intact.

Additional checks cover LOAD ONLY, LOAD HIGH, the zero-min/max high placement
case, command tails, child PSP/environment and inherited-handle cleanup,
repeated EXE/COM execution and exit status, free-memory accounting, and an
overlay end guard. Both kernels run Basic/XMS/EMS with 20/32 MiB. The exhaustive
table set runs in XMS/20 MiB; other profiles run the boundary subset. A persistent
blkdebug read failure leaves exactly 127 applied records and returns DOS error
13 in both OVERLAY and LOAD ONLY; the host checks the resulting filesystem.

A separate boot installs the pinned FreeDOS SHARE package, locks the sixth
relocation on behalf of another PSP, and checks both OVERLAY and LOAD ONLY.
Both kernels apply exactly five entries and return error 13. The test then
unlocks the range and checks successful loads and repeated EXE/COM execution.
The original package, including source, is retained in the CI artifact. Its
SHA-256 is `e9dd873b3f009f723def66204668d8932a4c60e8fdc32f6f93d02983f48d9a3f`;
the URL is pinned in scripts/libretto/exec.py.

The harness paints the disk API stack and records its untouched bottom margin,
with a 16-byte minimum gate. This is a high-water observation for these tests,
not a proof of a bound for every driver or interrupt handler.

## Measurement method

Benchmarks call the actual OVERLAY API, including open, seek, image read,
relocation and close, for 0/8/128/4096 entries in an 8 KiB image. Each marked
interval contains 16 calls. ABBA gives two boots per variant and five trials
per boot, or ten samples per scenario/variant. An additional ABBA sequence
compares identical baseline kernels to quantify noise.

Timed boots assert BUFFERS=-20: exactly 20 buffers with the same placement.
Separate positive-BUFFERS probes measure automatic HMA capacity. QEMU 8.2,
single-thread TCG, a fixed VM RTC and the repository instruction counter are
used. Counts exclude the ROM/VGA address window and include the test harness;
they are not native CPU cycles or predictions of game FPS.

## Initial scouting results (superseded candidate)

**These exact figures describe the initial 24-byte-frame candidate, not the
final SHARE-compatible revision.** The final revision keeps a 20-byte frame
and is 73211 bytes (+48 versus baseline). Current measurements and complete
CI status are attached to [PR #6](https://github.com/RabbitRu/freedos-libretto/pull/6).
The initial data is retained below to preserve its source and measurement
provenance; it must not be interpreted as SHARE validation.

The two CPU profiles use the same kernel code. Results below count non-ROM
instructions per 16 OVERLAY calls; each variant has ten samples per scenario.

| Relocation entries | Control median | Candidate median | Paired median change |
| ---: | ---: | ---: | ---: |
| 0 | 375987 | 376179 | +0.051% |
| 8 | 492611 | 409091 | -16.955% |
| 128 | 1966806 | 632515 | -67.840% |
| 4096 | 51319692 | 8617303 | -83.209% |

Identical-kernel calibration has 0.0000% median change in all four scenarios.
The zero-entry case gains no relocation-read saving and has a small added cost.
These figures describe the complete OVERLAY calls in the stated fixture, not
arbitrary program startup or gameplay.

| Resource | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| KERNEL.SYS bytes | 73163 | 73227 | +64 |
| Basic conventional free bytes | 509472 | 509408 | -64 |
| XMS/HMA conventional free bytes | 631200 | 631200 | 0 |
| EMS/UMB conventional free bytes | 637472 | 637472 | 0 |
| Automatic HMA disk buffers | 41 | 41 | 0 |
| Smallest observed disk-stack bottom margin | 22 | 18 | -4 |
| Disk-stack bottom margin in persistent-I/O-error test | 50 | 46 | -4 |

Memory values use the same MEMSTAT probe and agree at 20/32 MiB. Release kernels
are identical for the two tuning profiles. This initial candidate
grew the frame by four bytes. The final revision removes that growth. Neither
version enlarges the allocated API stack.

Raw samples, ranges, hashes and calibration reports are stored under
[measurements/2026-11-12/exec](measurements/2026-11-12/exec).
The measurement source contains 57 MZ fixtures. The final harness has 58
regular fixtures, a stack-margin gate and a separate real-SHARE case. The final
runtime additionally retains four-byte SHARE requests and removes frame growth;
it is measured again by CI. No current-result claim depends on the superseded
kernel hash in this archive.

Measurement run:
[43193923187](https://github.com/RabbitRu/freedos-libretto/actions/runs/43193923187).
Tested merge: `8749083b0115cb86bf10b52a0b8eb1cfccd1b909`;
tree `64e04041acb19612ddcb818bede97fc15cb5193c` matches the runtime implementation.
Artifact identities and verified ZIP digests are recorded in
[ci.json](measurements/2026-11-12/exec/ci.json). Final full-suite status is available
in the checks for [PR #6](https://github.com/RabbitRu/freedos-libretto/pull/6).

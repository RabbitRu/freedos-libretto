# DOS clock and calendar optimization

Baseline: `a961f142a1fc2d5554b7eed4b871c952cd5e6beb`.
Implementation: `32538ab29558cbedcefdc613b894073084cceaaa`.

## Changes

The built-in CLOCK$ driver keeps the original fixed-point result and resolution
with shorter arithmetic. The Watcom path uses 16-bit shift/add multiplication
and two DIV operations, reusing the remainder instead of repeatedly invoking
general division helpers. A high-word correction preserves the modulo-2^32
result for every input bit pattern. It uses no 32-bit registers, MMX or floating
point; other compilers retain the equivalent C expression.

BIOS INT 1Ah is called on every request, including consecutive same-tick queries.
Midnight counters and BIOS hooks remain observable. No time/date cache, validity
flags or resident data are added. External CLOCK$ drivers retain their existing
device-request path.

DaysToDate skips whole 1461-day cycles and examines at most four remaining year
boundaries. It handles non-leap 2100, including the shortened 2100–2103 cycle
and the transition into 2104. The WORD day range ends in 2159, before the next
exceptional century. Both DOS get-date and RTC writes use this helper.
Set-date validation remains 1980–2099.

## Validation

The host harness compiles actual systime.c/sysclk.c bodies with deterministic
BIOS/device stubs under ASan/UBSan. It checks all 65536 day counts/RTC BCD dates
against an independently advancing Gregorian calendar, and all 1573040 BIOS
ticks twice against the original formula. Further cases check BIOS-read counts,
midnight changes, a nested BIOS request, short requests and external drivers.
The host harness does not exercise 16-bit ABI or interrupt assembly.

A DOS executable compiles the exact production Watcom inline assembly extracted
from sysclk.c. It checks every valid BIOS tick, 100000 full-width pseudorandom
inputs and explicit wrap/high-word boundaries against the original C expression.

Real-kernel INT 21h tests check all 43830 supported dates, date/weekday round
trips, setters and invalid values, tick samples/repeated reads, leap/century
rollover, direct BIOS time changes, and a CLOCK$ driver installed through DEVICE.
Both kernels boot Basic/XMS/EMS at 20/32 MiB, the external-driver case and an
automatic-buffer probe. The exhaustive DOS date pass runs in XMS/20 MiB;
other profiles check month boundaries. The candidate's XMS/20 boot also runs
the exhaustive 16-bit arithmetic executable. Normal BIOS boots and existing
filesystem, memory/ABI, I/O-failure and diagnostic checks are separate CI steps.

## Measurement method

Actual INT 21h calls use a deterministic INT 1Ah fixture. Each interval has
256 calls. ABBA gives two boots per variant and five trials per boot: ten
samples per scenario/variant. A second ABBA sequence compares identical
baseline kernels to quantify noise. Raw intervals, medians, ranges and hashes
are retained with the results.

Timed boots use BUFFERS=-20 and assert runtime count/placement: exactly 20,
in HMA for XMS/EMS. Separate probes use ordinary positive BUFFERS=20 and assert
unchanged automatic capacity. This avoids the earlier compiler comparison's
HMA-capacity confound; ordinary boot profiles keep their allocation policy.

The metric counts guest instructions outside the ROM/VGA address window. It
includes the harness/BIOS fixture, not only kernel instructions. It is not
native CPU-cycle timing or a Libretto FPS prediction.

A cached candidate was evaluated first. The stateless version was selected
because it improves both time-query patterns, adds no resident state and
preserves HMA buffer capacity. Its file is also smaller.

## Results

Both CPU targets produce identical binaries and instruction-count results:

| Workload | Samples per variant | Change in non-ROM instructions |
| --- | ---: | ---: |
| Time, same tick | 10 | -5.5990% |
| Time, changing tick | 10 | -5.5990% |
| Date, 1980 | 10 | -3.8342% |
| Date, 2026 | 10 | -41.3854% |
| Date, 2099 | 10 | -63.9268% |
| Mixed time/date | 10 | -28.6445% |

Identical-kernel calibration has 0.0000% median change in every scenario for
both targets. All timed boots report exactly 20 buffers in HMA. Ordinary
positive-BUFFERS probes report 41 HMA buffers in both control and candidate.

| Resource | Master | Candidate | Change |
| --- | ---: | ---: | ---: |
| KERNEL.SYS bytes | 73195 | 73163 | -32 |
| Basic conventional free bytes | 509440 | 509472 | +32 |
| XMS/HMA conventional free bytes | 631200 | 631200 | 0 |
| EMS/UMB conventional free bytes | 637472 | 637472 | 0 |

Memory values are measured with the same MEMSTAT probe loaded, and agree at
20/32 MiB for both CPU profiles. Automatic buffer capacity is read from the
running kernel rather than inferred from conventional-memory values.

Raw measurements and calibrations:
[measurements/2026-11-12/clock](measurements/2026-11-12/clock).

CI run: [43177370357](https://github.com/RabbitRu/freedos-libretto/actions/runs/43177370357).
Tested merge: `70b7f0010a2a78a0b99978797907154eb9159da2`;
tree `4da94ed5dfe2fdd34502a334ef77e3989d408502` matches the implementation.
All four core CI jobs passed: **144 DOS boots** in total, including 48 clock
validation/measurement/calibration boots. The final documentation commit changes
no runtime code. Job identities, artifacts and verified ZIP digests are recorded
in [ci.json](measurements/2026-11-12/clock/ci.json).

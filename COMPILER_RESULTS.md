# Watcom settings: retain the size-oriented default

The accepted settings remain `-os`, with CPU profiles `-4` (486) and `-5` (Pentium MMX), 16-bit small model, `-r -zp1 -j -zgf -zff` and the existing Pascal helper ABI. No tested alternative reduced the measured instruction counts across the workloads.

[CI run 42954670025](https://github.com/RabbitRu/freedos-libretto/actions/runs/42954670025) completed all six jobs and 110 DOS boots, including 32 compiler-experiment boots. The compiler-only trials use source `e02d6d3611bd3950ba7580a9991d056c2d595304`, tested merge `62de02a4bacbe16d8ed231bf3d821e29a9d6aaa0`, tree `97a799d57317726dfce0fa2e34ac76efab03525b`. The same memory implementation is held fixed within every compiler comparison. A later assembly-only fixed-exit refinement is validated separately in [MEMORY_RESULTS.md](MEMORY_RESULTS.md); C defaults remain unchanged.

## Method and result

Each fitting setting uses fresh disks and ABBA order with two samples per workload/variant, the same pinned compiler/runtime and 20 MiB XMS/HMA. The first setting compares identical kernels and calibrates non-ROM count variation to at most 0.00013%. This is a screening experiment, not native cycle timing; alternate settings were not selected for release.

`scheduled-size` is `-os -ob -or -ol`; `scheduled` is `-os -or`. `hot-speed` keeps global `-os` and adds `-ot -ob -or -ol` only to blockio.c, fatfs.c and fattab.c. ABI, packing, signedness and memory model are held fixed.

| CPU | Setting | Kernel bytes | Write | Repeated read | Random read | Small files |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 486 | size | 72987 | 0.0000% | 0.0001% | 0.0000% | 0.0000% |
| 486 | scheduled-size | 73515 | 0.2494% | 0.3232% | 0.4081% | 0.0320% |
| 486 | scheduled | 73211 | 0.5843% | 0.5296% | 0.6101% | 0.3082% |
| 486 | hot-speed | 74507 | 8.4355% | 7.2513% | 11.1625% | 2.8046% |
| Pentium MMX | size | 72987 | 0.0000% | 0.0000% | 0.0000% | -0.0001% |
| Pentium MMX | scheduled-size | 73515 | 0.2490% | 0.3233% | 0.4081% | 0.0320% |
| Pentium MMX | scheduled | 73211 | 0.5843% | 0.5297% | 0.6101% | 0.3080% |
| Pentium MMX | hot-speed | 74507 | 8.4355% | 7.2513% | 11.1625% | 2.8047% |

Positive percentages mean more executed instructions outside the ROM/VGA address window. All fitting settings leave 631200 conventional bytes free under the XMS/HMA probe. They produce larger files without a demonstrated count reduction. Scheduling can affect real cycles independently of these counts; these results support retaining the established default pending hardware evidence.

The global `-ot` build fails to link: TGROUP exceeds 64 KiB by 2576 bytes. Global `-ot -ob -or -ol` exceeds it by 4464 bytes. The experiment records these rejections and continues; it does not change segment layout or ABI to bypass them.

## Reproduction and records

After the normal build/runtime setup, run `python3 scripts/libretto/compiler.py 486` or `python3 scripts/libretto/compiler.py pentium-mmx` in an isolated checkout. Alternatively enable the `compiler_scout` input on a manual workflow run. Ordinary PR validation skips this optional experiment.

`LIBRETTO_OPT` selects the global optimization bundle; `LIBRETTO_HOT_OPT` applies the extra bundle to the three named modules. They are experiment controls; production defaults stay `-os`. Successful future experiments archive and check C disassembly for high GPR/MMX use before comparison.

The committed [compiler summaries](measurements/2026-11-11/compiler) retain all medians/ranges, kernel hashes, memory results, overflow errors and artifact identities. Complete individual samples, comparison files, binaries, maps and build logs are in the compiler artifacts, subject to GitHub retention.

- [486 compiler experiment](https://github.com/RabbitRu/freedos-libretto/actions/runs/42954670025/artifacts/13826897301)
- [Pentium MMX compiler experiment](https://github.com/RabbitRu/freedos-libretto/actions/runs/42954670025/artifacts/13826897872)

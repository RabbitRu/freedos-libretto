# Initial measurements

Measured source: 7a35b092a3a31260a04b5b1dfb4313ce8d002a99.
[Successful CI run](https://github.com/RabbitRu/freedos-libretto/actions/runs/42772869459).
These are QEMU correctness and memory-layout measurements, not real-hardware
performance claims. Both CPUs and both RAM sizes produced the same
conventional-memory values below.

| Boot configuration | Free conventional bytes while probe runs | Largest free block | Difference from Basic |
| --- | ---: | ---: | ---: |
| Basic, DOS low, no XMS/EMS | 510400 | 510256 | 0 |
| XMS/HMA, HIMEMX, DOS high | 631280 | 631136 | +120880 |
| XMS/EMS/UMB, JemmEX, DOS high, DOSDATA=UMB | 637552 | 637408 | +127152 |

The probe occupies a 3440-byte PSP block. Measurements describe the state
while it runs as a child of FreeCOM, whose XMS-swap variant can move part of
itself out of conventional memory. The improvement is about 118.05 KiB for
XMS/HMA and 124.17 KiB for EMS/UMB. This is a configuration result, not a
reduction of the unchanged kernel binary.

Both kernels remain 72235 bytes with SHA-256
0687fd5f22fc984c95debf10294ca3a2f15705e7b4c0c0fabf4a659ec4511a74.

All 12 FAT32 runs passed: both CPUs, three configurations and 20/32 MiB RAM.
Each checked 12 boundary sizes and 1288568 assertions, host byte comparison,
256-fragment chains in both 128 KiB files, and fsck.fat. The four original
FAT12 boot tests passed as well.

DOSBENCH ran once per configuration to verify execution and valid CSV.
Those samples do not support a disk-speed claim. Actual Libretto comparisons
require repeated runs with documented hardware and cache conditions.

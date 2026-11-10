/* SPDX-License-Identifier: GPL-2.0-or-later
 * Diagnostic-only markers consumed by the QEMU plugin. No resident counters.
 * Normal builds emit no instructions and retain the original ABI/layout.
 */
#ifndef LIBRETTO_PROFILE_H
#define LIBRETTO_PROFILE_H
#ifdef LIBRETTO_PROFILE
#ifndef __WATCOMC__
#error LIBRETTO_PROFILE requires the Watcom diagnostic build
#endif
void lb_map(void);
void lb_chain(void);
void lb_back(void);
void lb_fat_read(void);
void lb_fat_write(void);
void lb_probe(void);
void lb_hit(void);
void lb_miss(void);
void lb_disk(void);
#pragma aux lb_map = 0x66 0xb8 1 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_chain = 0x66 0xb8 2 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_back = 0x66 0xb8 3 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_fat_read = 0x66 0xb8 4 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_fat_write = 0x66 0xb8 5 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_probe = 0x66 0xb8 6 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_hit = 0x66 0xb8 7 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_miss = 0x66 0xb8 8 0x50 0x42 0x4c modify exact [ax];
#pragma aux lb_disk = 0x66 0xb8 9 0x50 0x42 0x4c modify exact [ax];
#define LB_MAP() lb_map()
#define LB_CHAIN() lb_chain()
#define LB_BACK() lb_back()
#define LB_FAT_READ() lb_fat_read()
#define LB_FAT_WRITE() lb_fat_write()
#define LB_PROBE() lb_probe()
#define LB_HIT() lb_hit()
#define LB_MISS() lb_miss()
#define LB_DISK() lb_disk()
#else
#define LB_MAP() ((void)0)
#define LB_CHAIN() ((void)0)
#define LB_BACK() ((void)0)
#define LB_FAT_READ() ((void)0)
#define LB_FAT_WRITE() ((void)0)
#define LB_PROBE() ((void)0)
#define LB_HIT() ((void)0)
#define LB_MISS() ((void)0)
#define LB_DISK() ((void)0)
#endif
#endif

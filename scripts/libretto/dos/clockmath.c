/* SPDX-License-Identifier: GPL-2.0-or-later
 * Exercise the exact Watcom inline assembly extracted from sysclk.c.
 */
#include <stdio.h>
#include <stdlib.h>
typedef unsigned long ticks_t;
#define STATIC static
#include "clock-math-under-test.h"
static unsigned long reference(unsigned long raw)
{
    unsigned long n=raw*5UL;
    return ((n/59659UL)<<16)+((n%59659UL)<<16)/59659UL;
}
static void one(unsigned long raw)
{
    unsigned long a=ClockHundredths(raw),b=reference(raw);
    if (a!=b) { printf("FAIL: tick=%lu actual=%lu expected=%lu\n",raw,a,b); exit(1); }
}
int main(void)
{
    unsigned long raw,seed=7,i,edge=59659UL<<16;
    for (raw=0;raw<0x1800b0UL;raw++) one(raw);
    for (i=0;i<100000UL;i++) {
        seed=seed*1664525UL+1013904223UL;one(seed);
    }
    /* 5 has inverse CCCCCCCD modulo 2^32. Force the high-word boundary. */
    one((edge-1)*0xcccccccdUL);one(edge*0xcccccccdUL);
    one((edge+1)*0xcccccccdUL);one(0xffffffffUL);one(0x80000000UL);
    puts("PASS: actual 16-bit conversion, 1573040 BIOS ticks, 100000 full-width random inputs and overflow boundaries");
    return 0;
}

/****************************************************************/
/*                                                              */
/*                           sysclk.c                           */
/*                                                              */
/*                     System Clock Driver                      */
/*                                                              */
/*                      Copyright (c) 1995                      */
/*                      Pasquale J. Villani                     */
/*                      All Rights Reserved                     */
/*                                                              */
/* This file is part of DOS-C.                                  */
/*                                                              */
/* DOS-C is free software; you can redistribute it and/or       */
/* modify it under the terms of the GNU General Public License  */
/* as published by the Free Software Foundation; either version */
/* 2, or (at your option) any later version.                    */
/*                                                              */
/* DOS-C is distributed in the hope that it will be useful, but */
/* WITHOUT ANY WARRANTY; without even the implied warranty of   */
/* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See    */
/* the GNU General Public License for more details.             */
/*                                                              */
/* You should have received a copy of the GNU General Public    */
/* License along with DOS-C; see the file COPYING.  If not,     */
/* write to the Free Software Foundation, 675 Mass Ave,         */
/* Cambridge, MA 02139, USA.                                    */
/****************************************************************/

#include "portab.h"
#include "globals.h"

#ifdef VERSION_STRINGS
static char *RcsId =
    "$Id: sysclk.c 681 2003-09-09 17:32:20Z bartoldeman $";
#endif

/*                                                                      */
/* WARNING - THIS DRIVER IS NON-PORTABLE!!!!                            */
/*                                                                      */
UWORD ASM DaysSinceEpoch = 0;
typedef UDWORD ticks_t;

/* Cache only the tick-to-time conversion, never the BIOS read or date.
   A nested driver request uses its local record while this cache is busy. */
STATIC ticks_t clock_cache_tick;
STATIC UBYTE clock_cache[4];     /* minutes, hours, hundredths, seconds */
STATIC UBYTE clock_cache_valid;
STATIC volatile UBYTE clock_cache_busy;

STATIC int ByteToBcd(int x)
{
  return ((x / 10) << 4) | (x % 10);
}
/*
STATIC int BcdToByte(int x)
{
  return ((x >> 4) & 0xf) * 10 + (x & 0xf);
}
*/
STATIC void DayToBcd(BYTE * x, unsigned mon, unsigned day, unsigned yr)
{
  x[1] = ByteToBcd(mon);
  x[0] = ByteToBcd(day);
  x[3] = ByteToBcd(yr / 100);
  x[2] = ByteToBcd(yr % 100);
}

WORD ASMCFUNC FAR clk_driver(rqptr rp)
{
  BYTE bcd_days[4], bcd_minutes, bcd_hours, bcd_seconds;

  switch (rp->r_command)
  {
    case C_INIT:

      /* done in initclk.c */
      /* rp->r_endaddr = device_end(); not needed - bart */
      rp->r_nunits = 0;
      return S_DONE;

    case C_INPUT:
      {
        struct ClockRecord clk;
        int tmp;
        ticks_t ticks, raw_ticks;
        BOOL cacheable;

        if (sizeof(struct ClockRecord) != rp->r_count)
          return failure(E_LENGTH);

        raw_ticks = ReadPCClock();
        cacheable = !clock_cache_busy;
        if (cacheable)
        {
          clock_cache_busy = 1;
          if (clock_cache_valid && raw_ticks == clock_cache_tick)
          {
            fmemcpy(&clk.clkMinutes, clock_cache, sizeof(clock_cache));
            goto clock_ready;
          }
        }

        /* The scaling factor is now
           6553600/1193180 = 327680/59659 = 65536*5/59659 */

        ticks = 5 * raw_ticks;
        ticks = ((ticks / 59659u) << 16) + ((ticks % 59659u) << 16) / 59659u;

        tmp = (int)(ticks / 6000);
        clk.clkHours = tmp / 60;
        clk.clkMinutes = tmp % 60;

        tmp = (int)(ticks % 6000);
        clk.clkSeconds = tmp / 100;
        clk.clkHundredths = tmp % 100;

        if (cacheable)
        {
          fmemcpy(clock_cache, &clk.clkMinutes, sizeof(clock_cache));
          clock_cache_tick = raw_ticks;
          clock_cache_valid = 1;
        }

      clock_ready:
        if (cacheable)
          clock_cache_busy = 0;
        clk.clkDays = DaysSinceEpoch;

        fmemcpy(rp->r_trans, &clk, sizeof(struct ClockRecord));
      }
      return S_DONE;

    case C_OUTPUT:
      {
        struct dosdate date;
        struct ClockRecord clk;
        ticks_t hs, Ticks;

        if (sizeof(struct ClockRecord) != rp->r_count)
          return failure(E_LENGTH);

        fmemcpy(&clk, rp->r_trans, sizeof(struct ClockRecord));

        clock_cache_valid = 0;

        /* Set PC Clock first                                   */
        DaysSinceEpoch = clk.clkDays;
        hs = 6000 * (ticks_t)(60 * clk.clkHours + clk.clkMinutes) +
          (ticks_t)(100 * clk.clkSeconds + clk.clkHundredths);

        /* The scaling factor is now
           1193180/6553600 = 59659/327680 = 59659/65536/5 */

        Ticks = ((hs >> 16) * 59659u + (((hs & 0xffff) * 59659u) >> 16)) / 5;

        WritePCClock(Ticks);

        /* Use the same calendar conversion as DOS get-date. */
        DaysToDate(clk.clkDays, &date);
        DayToBcd(bcd_days, date.month, date.monthday, date.year);
        bcd_minutes = ByteToBcd(clk.clkMinutes);
        bcd_hours = ByteToBcd(clk.clkHours);
        bcd_seconds = ByteToBcd(clk.clkSeconds);
        WriteATClock(bcd_days, bcd_hours, bcd_minutes, bcd_seconds);
      }
      return S_DONE;

    case C_OFLUSH:
    case C_IFLUSH:
      return S_DONE;

    case C_OUB:
    case C_NDREAD:
    case C_OSTAT:
    case C_ISTAT:
    default:
      return failure(E_FAILURE);        /* general failure */
  }
}


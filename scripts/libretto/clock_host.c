/* SPDX-License-Identifier: GPL-2.0-or-later
 * Compiles the actual two kernel C modules with deterministic device stubs.
 * Calendar oracle advances one Gregorian day; time oracle retains the old
 * fixed-point calculation. This complements, not replaces, DOS boots.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t UWORD;
typedef int16_t WORD;
typedef uint32_t UDWORD;
typedef int8_t BYTE;
typedef uint8_t UBYTE;
typedef int BOOL;
#define STATIC static
#define ASM
#define FAR
#define ASMCFUNC
#define SUCCESS 0
#define DE_INVLDDATA -13
#define S_DONE 0x100
#define S_ERROR 0x8000
#define failure(x) (S_DONE | S_ERROR | (x))
struct ClockRecord { UWORD clkDays; UBYTE clkMinutes,clkHours,clkHundredths,clkSeconds; };
struct dostime { UBYTE hour,minute,second,hundredth; };
struct dosdate { UWORD year; UBYTE monthday,month; };
struct dhdr { int unused; };
typedef struct { UBYTE r_command; UWORD r_count,r_status; void *r_trans; UBYTE r_nunits; } request;
typedef request *rqptr;
static request ClkReqHdr;
static struct ClockRecord ClkRecord;
static struct dhdr *clock;
static UDWORD mock_tick,reads,writes;
static UBYTE midnight,rtc_date[4],rtc_h,rtc_m,rtc_s;
static int external;
static struct ClockRecord external_record,nested_record;
static WORD clk_driver(request *);
static UDWORD ReadPCClock(void);
static void WritePCClock(UDWORD);
static void WriteATClock(BYTE *,UBYTE,UBYTE,UBYTE);
static void BinaryCharIO(struct dhdr **,size_t,struct ClockRecord *,BYTE);
static int char_error(request *r,struct dhdr *d) { (void)r; (void)d; return -1; }
#define fmemcpy memcpy

#include "clock-under-test.h"

static void need(int ok,const char *why)
{
    if (!ok) { fprintf(stderr,"FAIL %s tick=%u day=%u\n",why,mock_tick,DaysSinceEpoch); exit(1); }
}
static UDWORD ReadPCClock(void)
{
    reads++; DaysSinceEpoch=(UWORD)(DaysSinceEpoch+midnight); midnight=0;
    return mock_tick;
}
static void WritePCClock(UDWORD n) { writes++; mock_tick=n; }
static void WriteATClock(BYTE *d,UBYTE h,UBYTE m,UBYTE s)
{
    memcpy(rtc_date,d,4); rtc_h=h; rtc_m=m; rtc_s=s;
}
static void BinaryCharIO(struct dhdr **d,size_t n,struct ClockRecord *c,BYTE command)
{
    request r;
    (void)d; r.r_command=(UBYTE)command; r.r_count=(UWORD)n; r.r_trans=c;
    if (external) {
        if (command==C_INPUT) *c=external_record;
        else external_record=*c;
        ClkReqHdr.r_status=S_DONE;
    } else ClkReqHdr.r_status=(UWORD)clk_driver(&r);
}
static void oracle(UDWORD raw,struct ClockRecord *r)
{
    UDWORD t=raw*5u,hs=((t/59659u)<<16)+((t%59659u)<<16)/59659u;
    unsigned m=hs/6000u,s=hs%6000u;
    r->clkHours=m/60; r->clkMinutes=m%60;
    r->clkSeconds=s/100; r->clkHundredths=s%100;
    r->clkDays=DaysSinceEpoch;
}
static UBYTE bcd(unsigned x) { return (UBYTE)((x/10)*16+x%10); }
int main(void)
{
    unsigned day,y=1980,m=1,d=1,limit,i;
    static const unsigned length[]={31,28,31,30,31,30,31,31,30,31,30,31};
    struct dosdate date;
    struct dostime time;
    struct dostime saved_cache;
    struct ClockRecord got,expected;
    request r={C_INPUT,sizeof(got),0,&got,0};
    for (day=0;day<65536;day++) {
        DaysToDate((UWORD)day,&date);
        need(date.year==y && date.month==m && date.monthday==d,"Gregorian date");
        if (y<=2099) need(DaysFromYearMonthDay(y,m,d)==day,"supported date round trip");
        got.clkDays=(UWORD)day; got.clkHours=12; got.clkMinutes=34;
        got.clkSeconds=56; got.clkHundredths=78;
        r.r_command=C_OUTPUT;
        need(clk_driver(&r)==S_DONE,"clock output");
        need(rtc_date[0]==bcd(d) && rtc_date[1]==bcd(m) &&
             rtc_date[2]==bcd(y%100) && rtc_date[3]==bcd(y/100),"RTC Gregorian BCD");
        need(rtc_h==0x12 && rtc_m==0x34 && rtc_s==0x56,"RTC time BCD");
        limit=length[m-1]+(m==2 && (y%4==0 && (y%100!=0 || y%400==0)));
        if (++d>limit) { d=1; if (++m>12) { m=1; y++; } }
    }
    r.r_command=C_INPUT;
    DaysSinceEpoch=12345; reads=0;
    for (mock_tick=0;mock_tick<0x1800b0u;mock_tick++) {
        oracle(mock_tick,&expected);
        for (i=0;i<2;i++) {
            need(clk_driver(&r)==S_DONE && !memcmp(&got,&expected,sizeof(got)),
                 "every BIOS tick, miss and hit");
        }
    }
    need(reads==2u*0x1800b0u,"BIOS still read on every cache hit");
    mock_tick=0; midnight=1; DaysSinceEpoch=100;
    clk_driver(&r); midnight=2; clk_driver(&r);
    need(got.clkDays==103,"fresh date on same-tick rollover");
    mock_tick=1000; clk_driver(&r); saved_cache=clock_cache;
    /* Model an interrupt while an outer request owns the cache. */
    clock_cache_busy=1; mock_tick=50000; r.r_trans=&nested_record;
    clk_driver(&r);
    oracle(50000,&expected);
    need(!memcmp(&nested_record,&expected,sizeof(expected)),"nested request local conversion");
    need(clock_cache_busy==1 && clock_cache_tick==1000 &&
         !memcmp(&clock_cache,&saved_cache,sizeof(saved_cache)),"nested request leaves outer cache untouched");
    clock_cache_busy=0; r.r_trans=&got;
    clk_driver(&r);
    need(!memcmp(&got,&expected,sizeof(got)),"cache after nested request");
    r.r_count=5; reads=0; writes=0;
    need(((UWORD)clk_driver(&r)&S_ERROR) && !reads,"reject short input");
    r.r_command=C_OUTPUT;
    need(((UWORD)clk_driver(&r)&S_ERROR) && !writes,"reject short output");
    external_record.clkDays=12345; external_record.clkHours=7;
    external_record.clkMinutes=8; external_record.clkSeconds=9;
    external_record.clkHundredths=10; external=1;
    DosGetTime(&time); need(time.hour==7 && time.hundredth==10,"external clock time");
    external_record.clkHours=11;
    DosGetTime(&time); need(time.hour==11,"external clock not cached");
    DosGetDate(&date);
    need(date.year==2013 && date.month==10 && date.monthday==19,"external clock date");
    puts("PASS: 65536 Gregorian days/RTC outputs, 1573040 ticks twice, BIOS reads, rollover, nesting, lengths, external driver");
    return 0;
}

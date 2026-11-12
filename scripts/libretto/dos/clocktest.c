/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <dos.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
void __cdecl clock_start(void);
void __cdecl clock_stop(void);
void __cdecl clock_ticks(unsigned long,unsigned,unsigned);
unsigned long __cdecl clock_stat(unsigned);
static unsigned active;
static void begin(void);
static void end(void);
#pragma aux begin = 0x66 0xb8 0x47 0x45 0x42 0x4c modify exact [ax];
#pragma aux end = 0x66 0xb8 0x44 0x4e 0x45 0x4c modify exact [ax];
static void need(int ok,const char *why)
{
    if (!ok) {
        if (active) { clock_stop(); active=0; }
        printf("FAIL: %s\n",why); exit(1);
    }
}
static void stop(void) { if (active) { clock_stop(); active=0; } }
static unsigned leap(unsigned y) { return y%4==0 && (y%100!=0 || y%400==0); }
static unsigned bcd(unsigned x) { return (x/10)*16+x%10; }
static void get(unsigned function,union REGS *r)
{
    memset(r,0,sizeof(*r)); r->h.ah=(unsigned char)function; intdos(r,r);
}
static unsigned setdate(unsigned y,unsigned m,unsigned d)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x2b; r.x.cx=y; r.h.dh=m; r.h.dl=d;
    intdos(&r,&r); return r.h.al;
}
static unsigned settime(unsigned h,unsigned m,unsigned s,unsigned hs)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x2d;
    r.h.ch=h; r.h.cl=m; r.h.dh=s; r.h.dl=hs;
    intdos(&r,&r); return r.h.al;
}
static void expect_time(unsigned long raw)
{
    union REGS r;
    unsigned long n=raw*5UL,hs=((n/59659UL)<<16)+((n%59659UL)<<16)/59659UL;
    unsigned minutes=(unsigned)(hs/6000UL),rest=(unsigned)(hs%6000UL);
    get(0x2c,&r);
    need(r.h.ch==minutes/60 && r.h.cl==minutes%60 &&
         r.h.dh==rest/100 && r.h.dl==rest%100,"tick conversion and repeated requests");
}
static void time_at(unsigned long raw)
{
    unsigned i;
    clock_ticks(raw,0,0);
    for (i=0;i<3;i++) expect_time(raw);
    need(clock_stat(0)==3,"BIOS read on every get-time");
}
static void correctness(int all_days)
{
    static const unsigned month_days[]={31,28,31,30,31,30,31,31,30,31,30,31};
    union REGS r;
    unsigned y,m,d,day=0,limit;
    unsigned long raw;
    for (y=1980;y<=2099;y++)
        for (m=1;m<=12;m++) {
            limit=month_days[m-1]+(m==2 && leap(y));
            for (d=1;d<=limit;d++,day++) {
                if (!all_days && d!=1 && d!=limit) continue;
                need(setdate(y,m,d)==0,"valid set-date");
                need(clock_stat(4)==(((unsigned long)(bcd(y/100)*256+bcd(y%100))<<16)|
                                     (bcd(m)*256+bcd(d))),"RTC date BCD");
                get(0x2a,&r);
                need(r.x.cx==y && r.h.dh==m && r.h.dl==d && r.h.al==(day+2)%7,
                     "date and weekday round trip");
            }
        }
    need(setdate(1900,1,1)==255 && setdate(2100,1,1)==255 &&
         setdate(2001,2,29)==255 && setdate(2000,0,1)==255 &&
         setdate(2000,13,1)==255 && setdate(2000,1,0)==255,"invalid dates rejected");
    for (raw=0;raw<0x1800b0UL;raw+=7919) time_at(raw);
    time_at(0); time_at(1); time_at(0x1800afUL);
    need(settime(12,34,56,78)==0 && clock_stat(3)==0x12345600UL,"RTC time BCD");
    raw=clock_stat(2); time_at(raw);
    need(settime(24,0,0,0)==255 && settime(0,60,0,0)==255 &&
         settime(0,0,60,0)==255 && settime(0,0,0,100)==255,"invalid times rejected");
    need(setdate(2000,2,28)==0,"set leap eve");
    clock_ticks(0,0,0); get(0x2c,&r);
    clock_ticks(0,1,0); get(0x2a,&r);
    need(r.x.cx==2000 && r.h.dh==2 && r.h.dl==29 && clock_stat(0)==1,
         "same-tick midnight updates leap date");
    clock_ticks(0,1,0); get(0x2a,&r);
    need(r.x.cx==2000 && r.h.dh==3 && r.h.dl==1,"same-tick next day");
    need(setdate(2099,12,31)==0,"set century eve");
    clock_ticks(0x1800afUL,0,0); get(0x2c,&r);
    clock_ticks(0,1,0); get(0x2c,&r); get(0x2a,&r);
    need(r.x.cx==2100 && r.h.dh==1 && r.h.dl==1 && clock_stat(0)==2,
         "century rollover counts midnight once");
    clock_ticks(123456,0,0); get(0x2c,&r);
    memset(&r,0,sizeof(r)); r.h.ah=1; r.x.dx=54321; int86(0x1a,&r,&r);
    expect_time(54321);
    stop();
    printf("PASS: %s supported dates, tick samples, BIOS reads, setters, leap/century rollover\n",
           all_days?"43830":"month-boundary");
}
static void external(void)
{
    union REGS r;
    /* The test CLOCK$ driver is loaded through DEVICE, not a patched kernel pointer. */
    need(setdate(2024,2,29)==0 && settime(7,8,9,10)==0,"external clock setters");
    clock_ticks(0,0,0);
    get(0x2c,&r);
    need(r.h.ch==7 && r.h.cl==8 && r.h.dh==9 && r.h.dl==10,"external exact time");
    need(settime(11,12,13,14)==0,"external clock replacement time");
    get(0x2c,&r);
    need(r.h.ch==11 && r.h.cl==12 && r.h.dh==13 && r.h.dl==14,"external fresh time");
    get(0x2a,&r);
    need(r.x.cx==2024 && r.h.dh==2 && r.h.dl==29 && clock_stat(0)==0,
         "external clock date without BIOS queries");
    stop(); puts("PASS: installed external CLOCK$ remains authoritative");
}
static void benchmark(void)
{
    static const char *names[]={"time_same_tick","time_changing_tick","date_1980","date_2026","date_2099","mixed"};
    union REGS r;
    unsigned trial,mode,i;
    puts("trial,scenario,calls,bios_reads");
    for (trial=0;trial<5;trial++)
        for (mode=0;mode<6;mode++) {
            need(setdate(mode==2?1980:mode==4?2099:2026,6,15)==0,"benchmark date");
            clock_ticks(123456,0,mode==1?1:0);
            get(0x2c,&r); /* Put both kernels in the same initial state. */
            begin();
            for (i=0;i<256;i++) get(mode>=2 && mode<=4?0x2a:mode==5 && (i&1)?0x2a:0x2c,&r);
            end();
            need(clock_stat(0)==257,"benchmark preserves BIOS polling");
            printf("%u,%s,256,%lu\n",trial,names[mode],clock_stat(0)-1);
        }
    stop();
}
int main(int argc,char **argv)
{
    union REGS r; struct SREGS s;
    unsigned buffers,location;
    need(argc==2,"mode");
    memset(&r,0,sizeof(r));segread(&s);r.h.ah=0x52;intdosx(&r,&r,&s);
    buffers=*(unsigned __far *)MK_FP(s.es,r.x.bx+0x3f);
    location=*(unsigned char __far *)MK_FP(s.es,r.x.bx+0x53);
    printf("CLOCK_CONFIG buffers=%u bufloc=%u\n",buffers,location);
    if (!strcmp(argv[1],"probe")) { puts("PASS: automatic buffer configuration"); return 0; }
    clock_start(); active=1; atexit(stop);
    if (!strcmp(argv[1],"bench")) benchmark();
    else if (!strcmp(argv[1],"external")) external();
    else correctness(!strcmp(argv[1],"all"));
    return 0;
}

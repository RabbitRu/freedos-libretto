/* SPDX-License-Identifier: GPL-2.0-or-later
 * Repeatable DOS I/O workload. Raw BIOS ticks, not a cycle-accurate emulator score.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <io.h>
#include <direct.h>
#include <sys/stat.h>
#include <dos.h>
/* Harmless 386+ MOV EAX markers for the optional QEMU counter plugin.
 * Values are unique signatures; they do not call an emulator-specific API.
 */
static void phase_begin(void);
static void phase_end(void);
#pragma aux phase_begin = 0x66 0xb8 0x47 0x45 0x42 0x4c modify exact [ax];
#pragma aux phase_end = 0x66 0xb8 0x44 0x4e 0x45 0x4c modify exact [ax];
static unsigned char data[4096];
static void need(int ok)
{
    if (!ok) { puts("ERROR: benchmark I/O failed"); exit(1); }
}
static unsigned long clock_ticks(void)
{
    union REGS in,out;
    memset(&in,0,sizeof(in));
    int86(0x1a,&in,&out);
    return ((unsigned long)out.x.cx<<16)|out.x.dx;
}
static unsigned long elapsed(unsigned long start)
{
    unsigned long now=clock_ticks();
    return now>=start ? now-start : now+0x1800b0UL-start;
}
static void reset_disk(void)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x0d; intdos(&r,&r);
}
int main(int argc,char **argv)
{
    unsigned repeats=argc>1 ? (unsigned)atoi(argv[1]) : 10;
    unsigned trial,i,j;
    unsigned long start,ticks,seed;
    int fd;
    char name[13];
    need(repeats>=1 && repeats<=100);
    for (i=0;i<sizeof(data);++i) data[i]=(unsigned char)(i*17u);
    need(mkdir("LBBENCH")==0); need(chdir("LBBENCH")==0);
    puts("scenario,run,bios_ticks,bytes,operations");
    for (trial=1;trial<=repeats;++trial) {
        fd=open("BENCH.BIN",O_CREAT|O_TRUNC|O_RDWR|O_BINARY,S_IREAD|S_IWRITE); need(fd>=0);
        start=clock_ticks(); phase_begin();
        for (i=0;i<256;++i) need(write(fd,data,sizeof(data))==sizeof(data));
        need(close(fd)==0); reset_disk(); phase_end(); ticks=elapsed(start);
        printf("write_1m_flush,%u,%lu,1048576,256\n",trial,ticks);
        fd=open("BENCH.BIN",O_RDONLY|O_BINARY); need(fd>=0);
        start=clock_ticks(); phase_begin();
        for (j=0;j<16;++j) {
            need(lseek(fd,0,SEEK_SET)==0);
            for (i=0;i<256;++i) need(read(fd,data,sizeof(data))==sizeof(data));
        }
        phase_end(); ticks=elapsed(start);
        printf("repeated_read_16m,%u,%lu,16777216,4096\n",trial,ticks);
        seed=1; start=clock_ticks(); phase_begin();
        for (i=0;i<2048;++i) {
            seed=seed*1664525UL+1013904223UL;
            need(lseek(fd,(long)((seed%2048)*512UL),SEEK_SET)>=0);
            need(read(fd,data,512)==512);
        }
        phase_end(); ticks=elapsed(start); need(close(fd)==0);
        printf("random_read_1m,%u,%lu,1048576,2048\n",trial,ticks);
        need(unlink("BENCH.BIN")==0);
        start=clock_ticks(); phase_begin();
        for (i=0;i<100;++i) {
            sprintf(name,"F%03u.BIN",i);
            fd=open(name,O_CREAT|O_TRUNC|O_RDWR|O_BINARY,S_IREAD|S_IWRITE); need(fd>=0);
            need(write(fd,data,17)==17); need(close(fd)==0);
        }
        for (i=0;i<100;++i) { sprintf(name,"F%03u.BIN",i); need(unlink(name)==0); }
        reset_disk(); phase_end(); ticks=elapsed(start);
        printf("small_files_100,%u,%lu,1700,100\n",trial,ticks);
    }
    need(chdir("..")==0); need(rmdir("LBBENCH")==0);
    return 0;
}

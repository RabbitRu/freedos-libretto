/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <io.h>
#include <dos.h>
#include <conio.h>
#include <sys/stat.h>
#include <share.h>
#include <errno.h>
#define LENGTH (256UL*1024)
static unsigned char buf[1024];
static unsigned long prefix;
static unsigned salt=1, tail=1;
static void need(int ok,const char *why)
{
    if (!ok) { printf("FAIL: %s\n",why); exit(1); }
}
static unsigned char value(unsigned long off,unsigned generation)
{
    return (unsigned char)(off*17UL+(off>>8)+(off>>16)*37UL+generation*53u);
}
static unsigned char expected(unsigned long off)
{
    return value(off,off<prefix?salt:tail);
}
static int create(const char *name)
{
    int fd=open(name,O_CREAT|O_TRUNC|O_RDWR|O_BINARY,S_IREAD|S_IWRITE);
    need(fd>=0,"create"); return fd;
}
static void fill(int fd,unsigned long begin,unsigned long end,unsigned generation)
{
    unsigned i,n;
    need(lseek(fd,(long)begin,SEEK_SET)==(long)begin,"fill seek");
    while (begin<end) {
        n=(unsigned)(end-begin>512?512:end-begin);
        for (i=0;i<n;i++) buf[i]=value(begin+i,generation);
        need(write(fd,buf,n)==n,"fill write"); begin+=n;
    }
}
static void make_fragmented(void)
{
    int a=create("TARGET.BIN"),b=create("OTHER.BIN");
    unsigned long off;
    for (off=0;off<LENGTH;off+=512) {
        fill(a,off,off+512,1); fill(b,off,off+512,4);
    }
    need(close(a)==0 && close(b)==0,"close fragmented files");
}
static void check_at(int fd,unsigned long off,unsigned n)
{
    unsigned i;
    int count;
    need(lseek(fd,(long)off,SEEK_SET)==(long)off,"random seek");
    count=read(fd,buf,n);
    if (count!=n) printf("read fd=%d off=%lu size=%u got=%d errno=%d\n",fd,off,n,count,errno);
    need(count==n,"random read");
    for (i=0;i<n;i++) need(buf[i]==expected(off+i),"random data");
}
static void probe(int fd)
{
    unsigned i;
    unsigned long seed=7, off;
    /* More than eight checkpoints, non-cluster-aligned and reverse reads. */
    for (i=0;i<160;i++) {
        seed=seed*1664525UL+1013904223UL;
        off=seed%(LENGTH-777);
        check_at(fd,off,777);
    }
    for (i=0;i<32;i++) check_at(fd,(31UL-i)*7001UL+3,513);
}
static int open_target(void)
{
    int fd=open("TARGET.BIN",O_RDWR|O_BINARY);
    need(fd>=0,"open target"); return fd;
}
static void handles(void)
{
    int fd=open_target(),other,copy;
    unsigned i;
    probe(fd);
    copy=dup(fd); need(copy>=0,"duplicate handle");
    check_at(copy,170003,513);
    need(tell(fd)==170516,"dup shares seek cursor");
    need(close(copy)==0,"close duplicate");
    other=sopen("TARGET.BIN",O_RDONLY|O_BINARY,SH_DENYNO);
    need(other>=0,"second independent handle");
    for (i=0;i<64;i++) {
        check_at(fd,(i*7919UL)%(LENGTH-777),777);
        check_at(other,((63-i)*3571UL)%(LENGTH-513),513);
    }
    need(close(other)==0 && close(fd)==0,"close handles");
    /* A different chain must not inherit TARGET's checkpoints. */
    fd=open("OTHER.BIN",O_RDONLY|O_BINARY); need(fd>=0,"open other chain");
    salt=tail=4; probe(fd); need(close(fd)==0,"close other chain");
    salt=tail=1; fd=open_target(); probe(fd); need(close(fd)==0,"reopen target");
}
static void resize(void)
{
    int fd=open_target(),copy;
    unsigned n;
    unsigned long off;
    probe(fd); copy=dup(fd); need(copy>=0,"dup for truncate");
    prefix=32771UL;
    need(lseek(copy,(long)prefix,SEEK_SET)==(long)prefix,"truncate seek");
    need(_dos_write(copy,buf,0,&n)==0 && n==0,"truncate through duplicate");
    need(filelength(fd)==(long)prefix,"duplicate observes length");
    need(close(copy)==0 && close(fd)==0,"close truncated file");
    /* Occupy freed clusters so regrowth follows a different chain. */
    copy=create("OCCUPY.BIN"); fill(copy,0,LENGTH,9); need(close(copy)==0,"occupy freed space");
    fd=open_target(); fill(fd,prefix,LENGTH,2); tail=2;
    need(close(fd)==0,"close expanded file"); fd=open_target(); probe(fd);
    need(lseek(fd,0,SEEK_SET)==0,"seek zero truncate");
    need(_dos_write(fd,buf,0,&n)==0 && n==0,"zero truncate");
    need(filelength(fd)==0,"empty length");
    fill(fd,0,LENGTH,3); prefix=0; salt=tail=3;
    need(close(fd)==0,"close regrown empty file"); fd=open_target(); probe(fd);
    off=LENGTH; need(lseek(fd,(long)off,SEEK_SET)==(long)off && read(fd,buf,1)==0,"regrown EOF");
    need(close(fd)==0,"close resize");
}
static void reuse(void)
{
    int fd=open_target(); probe(fd); need(close(fd)==0,"close before delete");
    need(unlink("TARGET.BIN")==0,"delete cached chain");
    fd=create("TARGET.BIN"); fill(fd,0,LENGTH,7); need(close(fd)==0,"close recreated file");
    salt=tail=7; fd=open_target(); probe(fd); need(close(fd)==0,"close recreate probe");
    fd=create("TARGET.BIN"); fill(fd,0,LENGTH,8); need(close(fd)==0,"close O_TRUNC file");
    salt=tail=8; fd=open_target(); probe(fd); need(close(fd)==0,"close O_TRUNC probe");
}
#pragma pack(push,1)
struct packet { unsigned long sector; unsigned count; void __far *buffer; };
#pragma pack(pop)
static void raw_write(unsigned long sector,unsigned char *data)
{
    union REGS r; struct SREGS s;
    struct packet p;
    p.sector=sector; p.count=1; p.buffer=data;
    memset(&r,0,sizeof(r)); segread(&s);
    r.x.ax=0x7305; r.x.cx=0xffff; r.x.dx=3; r.x.si=1;
    r.x.bx=FP_OFF(&p); s.ds=FP_SEG(&p);
    intdosx(&r,&r,&s);
    need(!r.x.cflag,"absolute FAT32 write");
}
static void rawfat(void)
{
    unsigned count,i;
    unsigned long sector;
    int fd=open_target(),cfg;
    probe(fd); need(close(fd)==0,"close before absolute writes");
    cfg=open("RAWCFG.BIN",O_RDONLY|O_BINARY); need(cfg>=0,"raw configuration");
    need(read(cfg,&count,2)==2,"raw count");
    for (i=0;i<count;i++) {
        need(read(cfg,&sector,4)==4 && read(cfg,buf,512)==512,"raw sector payload");
        raw_write(sector,buf);
    }
    need(close(cfg)==0,"close raw configuration");
    prefix=512; salt=1; tail=4;
    fd=open_target(); probe(fd); need(close(fd)==0,"close rewired file");
}
static void media(void)
{
    int fd=open("A:\\TARGET.BIN",O_RDONLY|O_BINARY);
    need(fd>=0,"open first floppy"); probe(fd); need(close(fd)==0,"close first floppy");
    outp(0xe9,'S'); outp(0xe9,'W'); outp(0xe9,'A'); outp(0xe9,'P');
    (void)getch();
    salt=tail=6;
    fd=open("A:\\TARGET.BIN",O_RDONLY|O_BINARY);
    need(fd>=0,"open changed floppy"); probe(fd); need(close(fd)==0,"close changed floppy");
}
int main(int argc,char **argv)
{
    need(argc==2,"mode");
    if (!strcmp(argv[1],"rawfat")) rawfat();
    else if (!strcmp(argv[1],"media")) media();
    else {
        make_fragmented();
        if (!strcmp(argv[1],"handles")) handles();
        else if (!strcmp(argv[1],"resize")) resize();
        else if (!strcmp(argv[1],"reuse")) reuse();
        else need(0,"unknown mode");
    }
    printf("PASS: %s\n",argv[1]); return 0;
}

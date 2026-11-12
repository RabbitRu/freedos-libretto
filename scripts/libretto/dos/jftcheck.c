/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <dos.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <process.h>

typedef unsigned char __far *table;
static unsigned pspseg;
static void need(int ok, const char *why)
{
    if (!ok) { printf("FAIL: %s\n", why); exit(1); }
}
static table current(void) { return *(table __far *)MK_FP(pspseg,0x34); }
static unsigned count(void) { return *(unsigned __far *)MK_FP(pspseg,0x32); }
static void install(table tab, unsigned n)
{
    *(table __far *)MK_FP(pspseg,0x34)=tab;
    *(unsigned __far *)MK_FP(pspseg,0x32)=n;
}
static unsigned resize(unsigned n)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x67; r.x.bx=n;
    intdos(&r,&r);
    return r.x.cflag ? r.x.ax : 0;
}
static unsigned owned(unsigned long *paras)
{
    union REGS r; struct SREGS s;
    unsigned seg,blocks=0,steps=0,size;
    unsigned char kind;
    memset(&r,0,sizeof(r)); segread(&s); r.h.ah=0x52;
    intdosx(&r,&r,&s);
    seg=*(unsigned __far *)MK_FP(s.es,r.x.bx-2); *paras=0;
    do {
        kind=*(unsigned char __far *)MK_FP(seg,0);
        need(kind=='M' || kind=='Z',"valid MCB chain");
        size=*(unsigned __far *)MK_FP(seg,3);
        if (*(unsigned __far *)MK_FP(seg,1)==pspseg) {
            blocks++; *paras+=size;
        }
        if (kind=='Z') break;
        need((unsigned long)seg+size+1<65536UL && ++steps<4096,
             "bounded MCB chain");
        seg+=size+1;
    } while (1);
    return blocks;
}
static void put(unsigned fd, char c)
{
    unsigned done;
    need(_dos_write(fd,&c,1,&done)==0 && done==1,"write preserved handle");
}
static unsigned duplicate(unsigned fd)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x45; r.x.bx=fd; intdos(&r,&r);
    need(!r.x.cflag,"duplicate handle"); return r.x.ax;
}
static void growth(void)
{
    static const unsigned sizes[]={40,80,160,20,40,81,161};
    unsigned base,copy,i,j,done,hold,largest,rc,oldcount;
    int fd;
    unsigned long baseparas,paras;
    table old;
    char arg[12],data[4];
    union REGS r;
    need(count()==20,"initial PSP JFT");
    need(_dos_creat("HANDLE.BIN",0,&fd)==0,"create inherited file");
    copy=duplicate(fd); put(fd,'A');
    base=owned(&baseparas);
    for (i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++) {
        oldcount=count();
        need(resize(sizes[i])==0,"resize JFT");
        need(count()==sizes[i],"updated PSP count");
        if (sizes[i]>oldcount)
            for (j=oldcount;j<sizes[i];j++)
                need(current()[j]==0xff,"new JFT entries are closed");
        need(owned(&paras)==base+1,"exactly one external JFT allocation");
        if (sizes[i]>oldcount)
            need(paras==baseparas+((unsigned long)sizes[i]+15)/16,
                 "old JFT paragraphs reclaimed");
    }
    put(copy,'B');
    sprintf(arg,"%u",fd);
    need(spawnl(P_WAIT,"JFTCHECK.EXE","JFTCHECK","child",arg,NULL)==0,
         "EXEC inherits live handles and child can grow JFT");
    need(owned(&paras)==base+1,"child allocations reclaimed");
    put(fd,'D');
    memset(&r,0,sizeof(r)); r.x.ax=0x4200; r.x.bx=fd; intdos(&r,&r);
    need(!r.x.cflag,"seek inherited file");
    need(_dos_read(fd,data,4,&done)==0 && done==4 && !memcmp(data,"ABCD",4),
         "duplicate and child share file position");

    /* Exhaust the large free block, then request a 64 KiB JFT. */
    need(_dos_allocmem(0xffff,&largest)!=0 && largest>4096,"largest block");
    need(_dos_allocmem(largest,&hold)==0,"hold free memory");
    old=current(); oldcount=count(); rc=resize(65535U);
    need(_dos_freemem(hold)==0,"release held memory");
    need(rc==8 && current()==old && count()==oldcount,
         "allocation failure leaves PSP and JFT unchanged");
    put(fd,'E');

    /* The old 16-bit (n+15) calculation wrapped at 65521. */
    need(resize(65521U)==0,"65521 handles without rounding overflow");
    need(*(unsigned __far *)MK_FP(FP_SEG(current())-1,3)==4096,
         "65521 handles allocate 4096 paragraphs");
    need(current()[65520U]==0xff,"last 65521 entry initialized");
    need(resize(65535U)==0,"65535 handles without rounding overflow");
    need(*(unsigned __far *)MK_FP(FP_SEG(current())-1,3)==4096 &&
         current()[65534U]==0xff,"last 65535 entry inside allocated block");
    need(owned(&paras)==base+1,"boundary growth frees old allocation");
    need(resize(20)==0 && resize(40)==0,"regrow after shrinking huge JFT");
    need(owned(&paras)==base+1 && paras==baseparas+3,
         "huge previous table reclaimed");
    need(_dos_close(copy)==0 && _dos_close(fd)==0,"close preserved handles");
    need(remove("HANDLE.BIN")==0,"remove handle fixture");
    puts("PASS: growth, shrink/regrow, memory, handles, EXEC, ENOMEM, 65521/65535");
}
static void external(unsigned mode)
{
    unsigned seg,i,owner;
    table tab,old=current();
    need(_dos_allocmem(16,&seg)==0,"allocate program-owned table");
    tab=MK_FP(seg,mode==1?16:0);
    for (i=0;i<256;i++) *((unsigned char __far *)MK_FP(seg,i))=0xa5;
    for (i=0;i<20;i++) tab[i]=old[i];
    owner=*(unsigned __far *)MK_FP(seg-1,1);
    if (mode) {
        /* A marker alone is insufficient: check offset and owner too. */
        static const char tag[8]={'F','D','J','F','T',0,0,0};
        for (i=0;i<8;i++) *((char __far *)MK_FP(seg-1,8+i))=tag[i];
        if (mode==2) *(unsigned __far *)MK_FP(seg-1,1)=8;
    }
    install(tab,20);
    need(resize(40)==0,"grow program-supplied JFT");
    need(*(unsigned __far *)MK_FP(seg-1,1)==(mode==2?8:owner),
         "program-supplied block not freed");
    for (i=0;i<20;i++) need(current()[i]==old[i],"external handles preserved");
    need(*((unsigned char __far *)MK_FP(seg,255))==0xa5,"external guard");
    *(unsigned __far *)MK_FP(seg-1,1)=owner;
    need(_dos_freemem(seg)==0,"caller releases external block");
    puts("PASS: custom JFT ownership/offset respected");
}
int main(int argc,char **argv)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x62; intdos(&r,&r); pspseg=r.x.bx;
    if (argc==3 && !strcmp(argv[1],"child")) {
        need(count()==20,"child inherits only PSP entries");
        need(resize(80)==0 && resize(160)==0,"child growth");
        put((unsigned)atoi(argv[2]),'C');
        return 0;
    }
    need(argc==2,"test mode");
    if (!strcmp(argv[1],"growth")) growth();
    else external((unsigned)atoi(argv[1]));
    return 0;
}

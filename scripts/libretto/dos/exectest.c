/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <dos.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <io.h>

typedef unsigned char __far *bytes;
#pragma pack(push,1)
struct fixture {
    char name[12];
    unsigned count, available, header, table, error, quick;
    unsigned long size;
};
struct parameters {
    unsigned env;
    void __far *tail;
    void __far *fcb1;
    void __far *fcb2;
    void __far *stack;
    void __far *entry;
};
#pragma pack(pop)
static unsigned parent, smallest=384;
static unsigned hard_errors;
static bytes diskstack;
static unsigned char buffer[4096], tail[]={8,' ','a','r','g',' ','1','2','3',13};
static void begin(void);
static void end(void);
#pragma aux begin = 0x66 0xb8 0x47 0x45 0x42 0x4c modify exact [ax];
#pragma aux end = 0x66 0xb8 0x44 0x4e 0x45 0x4c modify exact [ax];

static void need(int ok,const char *why)
{
    if (!ok) { printf("FAIL: %s\n",why); exit(1); }
}
static int __far disk_error(unsigned device,unsigned error,unsigned __far *header)
{
    (void)device;(void)error;(void)header;hard_errors++;
    _hardresume(_HARDERR_FAIL);return _HARDERR_FAIL;
}
static bytes at(unsigned seg,unsigned long pos)
{
    return MK_FP(seg+(unsigned)(pos>>4),(unsigned)pos&15);
}
static unsigned psp(void)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x62; intdos(&r,&r); return r.x.bx;
}
static void setpsp(unsigned seg)
{
    union REGS r;
    memset(&r,0,sizeof(r)); r.h.ah=0x50; r.x.bx=seg; intdos(&r,&r);
}
static unsigned exec(unsigned mode,const char *name,void *pb)
{
    union REGS r; struct SREGS s;
    memset(&r,0,sizeof(r)); segread(&s); r.x.ax=0x4b00+mode;
    r.x.dx=FP_OFF(name); s.ds=FP_SEG(name); r.x.bx=FP_OFF(pb); s.es=FP_SEG(pb);
    intdosx(&r,&r,&s); return r.x.cflag?r.x.ax:0;
}
static void water(void)
{
    unsigned i;
    for (i=0;i<384 && diskstack[i]==0x90;i++);
    if (i<smallest) smallest=i;
    need(i>=16,"disk API stack retains its bottom guard");
}
static void paint(void)
{
    unsigned i;
    for (i=0;i<384;i++) diskstack[i]=0x90;
}
static unsigned long freeparas(void)
{
    union REGS r; struct SREGS s;
    unsigned seg,n,steps=0; unsigned char kind;
    unsigned long total=0;
    /* A largest-block query coalesces free MCBs before comparing totals. */
    need(_dos_allocmem(0xffff,&n)!=0,"largest-block query must fail");
    memset(&r,0,sizeof(r));segread(&s);r.h.ah=0x52;intdosx(&r,&r,&s);
    seg=*(unsigned __far *)MK_FP(s.es,r.x.bx-2);
    do {
        kind=*(unsigned char __far *)MK_FP(seg,0);
        n=*(unsigned __far *)MK_FP(seg,3);
        need(kind=='M' || kind=='Z',"valid MCB chain");
        if (!*(unsigned __far *)MK_FP(seg,1)) total+=n;
        if (kind=='Z') break;
        need((unsigned long)seg+n+1<65536UL && ++steps<4096,"bounded MCB chain");
        seg+=n+1;
    } while (1);
    return total;
}
static void release_child(unsigned child)
{
    bytes handles=*(bytes __far *)MK_FP(child,0x34);
    unsigned i,n=*(unsigned __far *)MK_FP(child,0x32);
    unsigned env=*(unsigned __far *)MK_FP(child,0x2c);
    setpsp(child);
    for (i=0;i<n;i++) if (handles[i]!=255) need(_dos_close(i)==0,"close child handle");
    setpsp(parent);
    if (env) need(_dos_freemem(env)==0,"free child environment");
    need(_dos_freemem(child)==0,"free loaded child");
}
static void original(int fd,const struct fixture *f,unsigned expected)
{
    unsigned long pos; unsigned n,i;
    need(lseek(fd,(long)f->header*16,SEEK_SET)>=0,"seek original body");
    for (pos=0;pos<f->size;pos+=n) {
        n=(unsigned)((f->size-pos)>sizeof(buffer)?sizeof(buffer):f->size-pos);
        need(read(fd,buffer,n)==n,"read original body");
        for (i=0;i<n;i++) at(expected,pos)[i]=buffer[i];
    }
}
static void reference(int fd,const struct fixture *f,unsigned expected,unsigned delta)
{
    unsigned left=f->available,n,i,value,off,seg;
    unsigned long target;
    need(lseek(fd,f->table,SEEK_SET)>=0,"seek reference table");
    while (left) {
        n=left>1024?1024:left;
        need(read(fd,buffer,n*4)==n*4,"read independent reference table");
        for (i=0;i<n;i++) {
            off=buffer[4*i]+256U*buffer[4*i+1];
            seg=buffer[4*i+2]+256U*buffer[4*i+3];
            target=(unsigned long)seg*16+off;
            need(target+1<f->size,"fixture target within image");
            value=at(expected,target)[0]+256U*at(expected,target+1)[0]+delta;
            at(expected,target)[0]=(unsigned char)value;
            at(expected,target+1)[0]=(unsigned char)(value>>8);
        }
        left-=n;
    }
}
static void equal(unsigned a,unsigned b,unsigned long size)
{
    unsigned long pos;
    for (pos=0;pos<size;pos++)
        if (*at(a,pos)!=*at(b,pos)) {
            printf("DIFFERENCE offset=%lu expected=%u actual=%u\n",pos,*at(a,pos),*at(b,pos));
            need(0,"relocated image matches byte oracle");
        }
}
static void check(const struct fixture *f,unsigned mode)
{
    struct parameters pb; unsigned overlay[2];
    unsigned expected,loaded=0,child=0,rc,env,paras;
    int fd;
    unsigned long before;
    void __far *dta;
    union REGS r;struct SREGS s;
    memset(&r,0,sizeof(r));segread(&s);r.h.ah=0x2f;intdosx(&r,&r,&s);dta=MK_FP(s.es,r.x.bx);
    before=freeparas();
    paras=(unsigned)((f->size+15)/16);
    need(_dos_allocmem(paras,&expected)==0,"allocate oracle image");
    fd=open(f->name,O_RDONLY|O_BINARY);need(fd>=0,"open fixture");
    original(fd,f,expected);
    memset(&pb,0,sizeof(pb));pb.tail=tail;pb.fcb1=MK_FP(parent,0x5c);pb.fcb2=MK_FP(parent,0x6c);
    if (mode==3) {
        need(_dos_allocmem(paras+1,&loaded)==0,"allocate overlay and guard");
        _fmemset(at(loaded,f->size),0xa5,16); /* size is paragraph aligned */
        overlay[0]=loaded;overlay[1]=0x1234;
    }
    paint();
    rc=exec(mode,f->name,mode==3?(void *)overlay:(void *)&pb);
    if (!rc && mode!=3) {
        child=psp();setpsp(parent);
        /* FreeDOS copies the return block only for AL=1, not AL=81h. */
        loaded=mode==1?FP_SEG(pb.entry):child+16;
    }
    water();
    if (rc!=f->error) printf("RETURN %s mode=%u expected=%u actual=%u INT24=%u\n",f->name,mode,f->error,rc,hard_errors);
    need(rc==f->error,"EXEC return code");
    if (!rc || mode==3) {
        reference(fd,f,expected,mode==3?0x1234:loaded);
        if (f->quick==2 && mode!=3) {
            need(FP_SEG(pb.stack)==loaded && FP_OFF(pb.stack)==0xfe,
                 "zero min/max places the image high and returns its stack");
            need(*(unsigned __far *)pb.stack==0,"LOAD ONLY pushes valid FCB status");
            at(expected,0xfe)[0]=at(expected,0xff)[0]=0;
        }
        equal(expected,loaded,f->size);
    }
    if (mode==3) {
        unsigned i;
        for (i=0;i<16;i++) need(at(loaded,f->size)[i]==0xa5,"overlay end guard");
        need(_dos_freemem(loaded)==0,"free overlay");
    } else if (!rc) {
        bytes cmd=MK_FP(child,0x80); unsigned i;
        for (i=0;i<sizeof(tail);i++) need(cmd[i]==tail[i],"command tail preserved");
        env=*(unsigned __far *)MK_FP(child,0x2c);
        need(env!=0 && child!=parent,"child PSP and environment");
        release_child(child);
    }
    memset(&r,0,sizeof(r));segread(&s);r.h.ah=0x1a;
    s.ds=FP_SEG(dta);r.x.dx=FP_OFF(dta);intdosx(&r,&r,&s);
    need(close(fd)==0 && _dos_freemem(expected)==0,"release reference data");
    need(freeparas()==before,"EXEC preserves free memory after cleanup/error");
    printf("PASS: %s mode=%u records=%u available=%u error=%u\n",f->name,mode,f->count,f->available,rc);
}
static void execute(void)
{
    struct parameters pb; union REGS r;
    unsigned i; unsigned long before=freeparas();
    memset(&pb,0,sizeof(pb));pb.tail=tail;pb.fcb1=MK_FP(parent,0x5c);pb.fcb2=MK_FP(parent,0x6c);
    for (i=0;i<8;i++) {
        paint();need(exec(0,"RUN.EXE",&pb)==0,"load and execute EXE");water();
        memset(&r,0,sizeof(r));r.h.ah=0x4d;intdos(&r,&r);need(r.x.ax==7,"EXE child exit status");
        need(exec(0,"RUN.COM",&pb)==0,"COM regression");
        memset(&r,0,sizeof(r));r.h.ah=0x4d;intdos(&r,&r);need(r.x.ax==7,"COM child exit status");
    }
    need(freeparas()==before,"repeated EXEC reclaims child blocks");
    puts("PASS: repeated EXE/COM execution, inherited stdout, exit status, memory");
}
static void bench(void)
{
    static const char *names[]={"B0.EXE","B8.EXE","B128.EXE","B4096.EXE"};
    unsigned seg,pb[2],trial,scenario,i;
    need(_dos_allocmem(512,&seg)==0,"benchmark overlay memory");pb[0]=seg;pb[1]=0x1234;
    puts("trial,scenario,calls");
    for (trial=0;trial<5;trial++) for (scenario=0;scenario<4;scenario++) {
        need(exec(3,names[scenario],pb)==0,"warm overlay");
        begin();
        for (i=0;i<16;i++) need(exec(3,names[scenario],pb)==0,"benchmark overlay");
        end();
        printf("%u,%s,16\n",trial,names[scenario]);
    }
    need(_dos_freemem(seg)==0,"free benchmark image");
}
int main(int argc,char **argv)
{
    union REGS r;struct SREGS s;struct fixture f;
    unsigned n=0;int fd;
    need(argc==2,"mode");parent=psp();
    memset(&r,0,sizeof(r));segread(&s);r.h.ah=0x52;intdosx(&r,&r,&s);
    printf("EXEC_CONFIG buffers=%u bufloc=%u\n",*(unsigned __far *)MK_FP(s.es,r.x.bx+0x3f),
           *(unsigned char __far *)MK_FP(s.es,r.x.bx+0x53));
    if (!strcmp(argv[1],"probe")) { puts("PASS: automatic buffers");return 0; }
    memset(&r,0,sizeof(r));segread(&s);r.x.ax=0x5d06;intdosx(&r,&r,&s);
    diskstack=MK_FP(s.ds,r.x.si+0x480);
    if (!strcmp(argv[1],"bench")) { bench();return 0; }
    if (!strcmp(argv[1],"io")) {
        memset(&f,0,sizeof(f));strcpy(f.name,"AIO.EXE");
        f.count=256;f.available=127;f.header=2;f.table=0x3001;f.error=13;f.size=8160;
        _harderr(disk_error);check(&f,3);check(&f,1);
        need(hard_errors>=2,"real INT 24 disk failures reached both loads");
        printf("PASS: persistent relocation-table disk error; INT24 calls=%u; disk-stack untouched margin=%u of 384 bytes\n",hard_errors,smallest);
        return 0;
    }
    fd=open("CASES.DAT",O_RDONLY|O_BINARY);need(fd>=0,"open fixture metadata");
    while (read(fd,&f,sizeof(f))==sizeof(f)) {
        if (!f.quick && strcmp(argv[1],"all")) continue;
        check(&f,3);check(&f,1);
        if (!f.error && f.quick==1) check(&f,0x81);
        n++;
    }
    need(close(fd)==0 && n!=0,"complete fixture metadata");execute();
    printf("PASS: %u fixtures; disk-stack untouched margin=%u of 384 bytes\n",n,smallest);
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Compile the actual relocation block with traced local/redirector reads. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint16_t UWORD;
typedef int16_t COUNT;
typedef UWORD seg;
typedef void VOID;
static UWORD ExeRelocs[16];
#define FAR
#define OVERLAY 3
#define XFR_READ 0
#define SFT_FSHARED 0x8000
#define DE_INVLDDATA (-13)
#define min(a,b) ((a)<(b)?(a):(b))
static unsigned char image[8192],expected[8192],table[65535UL*4];
#define MK_FP(s,o) ((void *)(image+(uint16_t)(s)*16+(uint16_t)(o)))
static struct { UWORD exRelocItems,exRelocTable; } ExeHeader;
static struct { UWORD sft_flags; COUNT sft_shroff; } sft, *lpCurSft;
typedef struct { struct { UWORD reloc; } load; } exec_blk;
static unsigned available,position,calls,largest,freed,negative;
static void SftSeek(COUNT fd,UWORD offset,unsigned origin)
{
    (void)fd;(void)offset;(void)origin;position=0;lpCurSft=&sft;
}
static long DosRWSft(COUNT fd,unsigned length,void *dst,unsigned direction)
{
    unsigned n=available-position;
    (void)fd;(void)direction;
    calls++;if (length>largest) largest=length;
    if (!n && negative) return -1;
    if (n>length) n=length;
    memcpy(dst,table+position,n);position+=n;return n;
}
static void DosMemFree(UWORD segment) { (void)segment;freed++; }
static int run(unsigned mode)
{
    UWORD start_seg=0,mem=0,env=0;
    COUNT fd=0;
    exec_blk params={{0x1234}}, *exp=&params;
#include "exec-under-test.h"
    return 0;
}
static unsigned get16(const unsigned char *p) { return p[0]+256U*p[1]; }
static void one(unsigned count,unsigned bytes,unsigned remote,unsigned fail,unsigned mode)
{
    unsigned i,complete,off,value,wanted,rc;
    for (i=0;i<sizeof(image);i++) image[i]=expected[i]=(unsigned char)(i*37+(i>>8));
    ExeHeader.exRelocItems=(UWORD)count;
    available=bytes;calls=largest=freed=0;negative=fail;
    sft.sft_flags=remote==1?SFT_FSHARED:0;sft.sft_shroff=remote==2?0:-1;
    complete=bytes/4;if (complete>count) complete=count;
    for (i=0;i<complete;i++) {
        off=get16(table+4*i)+16*get16(table+4*i+2);
        value=get16(expected+off)+(mode==OVERLAY?0x1234:0);
        expected[off]=(unsigned char)value;expected[off+1]=(unsigned char)(value>>8);
    }
    rc=run(mode);
    assert((int)rc==(bytes>=count*4?0:DE_INVLDDATA));
    assert(!memcmp(image,expected,sizeof(image)));
    assert(freed==(mode!=OVERLAY && bytes<count*4?2U:0U));
    wanted=remote?4:32;
    assert(largest==(count?min(count*4,wanted):0));
    assert(calls==(bytes>=count*4?(count+(remote?0:7))/(remote?1:8):bytes/wanted+1));
}
int main(void)
{
    static const unsigned counts[]={0,1,7,8,9,15,16,17,127,128,129,16383,16384,16385,32767,32768,65535};
    static const unsigned offsets[]={0x200,0x201,0x200,0x1f0,0x400,0x600};
    unsigned i,j,k,n=0,off;
    for (i=0;i<65535;i++) {
        off=offsets[i%6];table[4*i]=(unsigned char)off;table[4*i+1]=(unsigned char)(off>>8);
        table[4*i+2]=(unsigned char)(i%6==3);table[4*i+3]=0;
    }
    for (i=0;i<sizeof(counts)/sizeof(counts[0]);i++)
        for (j=0;j<3;j++) { one(counts[i],counts[i]*4,j,0,OVERLAY);n++; }
    for (i=0;i<68;i++) for (j=0;j<3;j++) for (k=0;k<2;k++) {
        one(17,i,j,k,OVERLAY);one(17,i,j,k,1);n+=2;
    }
    printf("PASS: %u actual-block cases; local/remote/SHARE request sizes, prefixes, negative reads, cleanup, byte oracle\n",n);
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Independent byte oracle plus complete destination-segment checks.
 * The assembly wrapper calls kernel/asmsupt.asm, not a C library substitute.
 */
#include <dos.h>
#include <stdio.h>
#include <stdlib.h>

unsigned __cdecl checked(unsigned, void __far *, void __far *, unsigned, unsigned);
static unsigned char near_src[2048], near_dst[2048];
static unsigned char __far *src;
static unsigned char __far *dst;
static unsigned char __far *ref;
static unsigned long cases;
static void need(int ok, const char *why)
{
    if (!ok) { printf("FAIL %s case=%lu\n",why,cases); exit(1); }
}
static void one(unsigned op, unsigned d, unsigned s, unsigned n, unsigned ch,
                int same, int alias)
{
    unsigned i,j,k,segment;
    unsigned char __far *a;
    unsigned char __far *b;
    unsigned char __far *r;
    ++cases;
    if (!(op&1)) {
        a=(unsigned char __far *)near_dst;
        b=same ? a : (unsigned char __far *)near_src;
        r=ref;
        segment=sizeof(near_dst);
    } else {
        a=dst; b=same ? a : src; r=ref; segment=0;
    }
    /* segment=0 denotes the full 65536-byte offset space. */
    i=0;
    do { a[i]=r[i]=(unsigned char)(i*29u+7u); ++i; } while (i!=segment);
    if (!same) {
        i=0;
        do { b[i]=(unsigned char)(i*17u+53u); ++i; } while (i!=segment);
    }
    /* Forward word copies are the old implementation's overlap semantics. */
    for (i=0;i<(n>>1);++i) {
        j=s+(i<<1); k=d+(i<<1);
        if (op>=2) { r[k]=(unsigned char)ch; r[(unsigned)(k+1)]=(unsigned char)ch; }
        else {
            unsigned char lo=same ? r[j] : b[j];
            unsigned char hi=same ? r[(unsigned)(j+1)] : b[(unsigned)(j+1)];
            r[k]=lo; r[(unsigned)(k+1)]=hi;
        }
    }
    if (n&1) r[(unsigned)(d+n-1)]=op>=2 ? (unsigned char)ch :
        (same ? r[(unsigned)(s+n-1)] : b[(unsigned)(s+n-1)]);
    a=MK_FP(FP_SEG(a),FP_OFF(a)+d); b=MK_FP(FP_SEG(b),FP_OFF(b)+s);
    if (alias) b=MK_FP(FP_SEG(b)-1,FP_OFF(b)+16);
    need(checked(op,a,b,n,ch)==0,"ABI/DF/registers");
    a=MK_FP(FP_SEG(a),0);
    /* For near arrays, offset zero is not the start of the array. */
    if (!(op&1)) a=(unsigned char __far *)near_dst;
    i=0;
    do {
        if (a[i]!=r[i]) {
            printf("op=%u d=%u s=%u n=%u byte=%u actual=%u expected=%u\n",
                   op,d,s,n,i,a[i],r[i]);
            need(0,"data/guard");
        }
        ++i;
    } while (i!=segment);
}
int main(void)
{
    unsigned a,b,c,op,ss,ds,rs,i;
    static const unsigned lengths[]={0,1,2,3,4,7,15,16,31,32,63,64,65,66,67,
                                    127,128,129,255,256,257,511,512,513,1023};
    static const unsigned large[]={1024,4095,4096,32767,32768,65532,65533,65534,65535};
    /* Release the C runtime's unused DOS allocation before requesting segments. */
    need(_dos_allocmem(4096,&ss)==0,"source allocation");
    need(_dos_allocmem(4096,&ds)==0,"destination allocation");
    need(_dos_allocmem(4096,&rs)==0,"oracle allocation");
    src=MK_FP(ss,0); dst=MK_FP(ds,0); ref=MK_FP(rs,0);
    for (op=0;op<4;++op)
        for (i=0;i<sizeof(lengths)/sizeof(lengths[0]);++i)
            for (a=0;a<4;++a)
                for (b=0;b<4;++b) {
                    c=(i&1) ? 0x12a5 : 0;
                    one(op,32+a,64+b,lengths[i],c,0,0);
                }
    for (i=0;i<sizeof(large)/sizeof(large[0]);++i) {
        one(1,0,0,large[i],0,0,0);
        one(3,0,0,large[i],0x12a5,0,0);
    }
    /* Segment wrapping aligned to words, exact end, and the last byte. */
    one(1,0xffe0,0xffe0,128,0,0,0);
    one(3,0xffe0,0,128,0x5a,0,0);
    one(1,0xff00,0xff00,256,0,0,0);
    one(3,0xff00,0,256,0xff,0,0);
    one(1,0xffff,0xffff,1,0,0,0);
    one(3,0xffff,0,1,0x1234,0,0);
    for (a=0;a<8;++a) {
        one(1,64+a,64,512,0,1,0);
        one(1,64,64+a,512,0,1,0);
        one(1,64+a,64,512,0,1,1);
    }
    printf("PASS cases=%lu full destination and ABI checks\n",cases);
    _dos_freemem(ss); _dos_freemem(ds); _dos_freemem(rs);
    return 0;
}

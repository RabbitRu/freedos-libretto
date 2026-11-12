/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <dos.h>
#include <stdio.h>
#include <stdlib.h>
void __pascal kcopy(void *,const void *,unsigned);
void __pascal kfcopy(void __far *,const void __far *,unsigned);
void __pascal kfill(void *,int,unsigned);
void __pascal kffill(void __far *,int,unsigned);
#pragma aux (__pascal) pascal_ax __modify __exact [__ax]
#pragma aux (pascal_ax) kcopy "MEMCPY"
#pragma aux (pascal_ax) kfcopy "FMEMCPY"
#pragma aux (pascal_ax) kfill "MEMSET"
#pragma aux (pascal_ax) kffill "FMEMSET"
static void begin(void);
static void end(void);
#pragma aux begin = 0x66 0xb8 0x47 0x45 0x42 0x4c modify exact [ax];
#pragma aux end = 0x66 0xb8 0x44 0x4e 0x45 0x4c modify exact [ax];
static unsigned char near_src[2048],near_dst[2048];
int main(void)
{
    unsigned ss,ds,op,i,j,a,n,trial,da,sa;
    unsigned char *ns=near_src+((-FP_OFF(near_src))&3);
    unsigned char *nd=near_dst+((-FP_OFF(near_dst))&3);
    unsigned char __far *src;
    unsigned char __far *dst;
    static const unsigned lengths[]={0,1,8,16,32,63,64,65,128,256,512,1024,4096,32768,65532};
    if (_dos_allocmem(4096,&ss) || _dos_allocmem(4096,&ds)) return 1;
    src=MK_FP(ss,0); dst=MK_FP(ds,0);
    puts("trial,op,bytes,dest_alignment,source_alignment,calls");
    for (trial=0;trial<3;++trial)
        for (op=0;op<4;++op)
            for (i=0;i<sizeof(lengths)/sizeof(lengths[0]);++i)
                for (a=0;a<4;++a) {
                    n=lengths[i];
                    if (!(op&1) && n>1024) continue;
                    da=a<2 ? a : 0; sa=a<2 ? a : a-1;
                    begin();
                    for (j=0;j<128;++j) {
                        switch (op) {
                        case 0: kcopy(nd+da,ns+sa,n); break;
                        case 1: kfcopy(dst+da,src+sa,n); break;
                        case 2: kfill(nd+da,0x12a5,n); break;
                        default: kffill(dst+da,0x12a5,n); break;
                        }
                    }
                    end();
                    printf("%u,%u,%u,%u,%u,128\n",trial,op,n,da,sa);
                }
    _dos_freemem(ss); _dos_freemem(ds);
    return 0;
}

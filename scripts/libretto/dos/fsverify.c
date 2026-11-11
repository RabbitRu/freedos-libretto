/* SPDX-License-Identifier: GPL-2.0-or-later
 * File operations through the DOS C runtime; host checks independent output.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <io.h>
#include <direct.h>
#include <sys/stat.h>
#include <dos.h>

static unsigned char buffer[4098];
static unsigned long checks;
static void require(int ok, const char *operation)
{
    ++checks;
    if (!ok) { printf("FAIL: %s (check %lu)\n", operation, checks); exit(1); }
}
static unsigned char pattern(unsigned long offset, unsigned seed)
{
    return (unsigned char)(((offset * 17UL) + (offset >> 8)) ^ seed);
}
static void fill(unsigned long off, unsigned n, unsigned seed)
{
    unsigned i;
    for (i=0; i<n; ++i) buffer[i+1] = pattern(off+i, seed);
}
static int create(const char *name)
{
    int fd = open(name, O_CREAT|O_TRUNC|O_RDWR|O_BINARY, S_IREAD|S_IWRITE);
    require(fd >= 0, "create");
    return fd;
}
static void close_ok(int fd) { require(close(fd)==0, "close"); }
static void verify(const char *name, unsigned long size, unsigned seed)
{
    unsigned long off=0;
    unsigned n, i;
    int fd=open(name, O_RDONLY|O_BINARY);
    require(fd>=0, "open for read");
    while (off<size) {
        n=(unsigned)((size-off)>2047 ? 2047 : size-off);
        require(read(fd, buffer+1, n)==n, "read count");
        for (i=0; i<n; ++i) require(buffer[i+1]==pattern(off+i, seed), "read data");
        off+=n;
    }
    require(read(fd,buffer+1,1)==0, "EOF");
    if (size) {
        off=size/2;
        require(lseek(fd,(long)off,SEEK_SET)==(long)off, "seek");
        require(read(fd,buffer+1,1)==1 && buffer[1]==pattern(off,seed), "seek data");
    }
    close_ok(fd);
}
static void boundary(unsigned long size)
{
    unsigned long off=0;
    unsigned n;
    int fd=create("BOUND.BIN");
    while (off<size) {
        n=(unsigned)((size-off)>4093 ? 4093 : size-off);
        fill(off,n,0x5a);
        require(write(fd,buffer+1,n)==n,"write count");
        off+=n;
    }
    close_ok(fd);
    verify("BOUND.BIN",size,0x5a);
    fd=open("BOUND.BIN",O_RDWR|O_BINARY);
    require(fd>=0,"reopen");
    require(lseek(fd,0,SEEK_END)==(long)size,"seek end");
    fill(size,17,0x5a);
    require(write(fd,buffer+1,17)==17,"append");
    close_ok(fd);
    verify("BOUND.BIN",size+17,0x5a);
    fd=open("BOUND.BIN",O_RDWR|O_BINARY);
    require(fd>=0,"reopen for truncate");
    require(chsize(fd,(long)(size/2))==0,"truncate");
    close_ok(fd);
    verify("BOUND.BIN",size/2,0x5a);
    require(rename("BOUND.BIN","RENAMED.BIN")==0,"rename");
    verify("RENAMED.BIN",size/2,0x5a);
    require(unlink("RENAMED.BIN")==0,"delete");
}
int main(void)
{
    static const unsigned long sizes[]={0,1,511,512,513,4095,4096,4097,65535UL,65536UL,65537UL,131091UL};
    unsigned i;
    unsigned long off;
    int a,b;
    union REGS r;
    require(mkdir("FSWORK")==0,"mkdir");
    require(chdir("FSWORK")==0,"chdir");
    for (i=0; i<sizeof(sizes)/sizeof(sizes[0]); ++i) boundary(sizes[i]);
    a=create("FRAGA.BIN"); b=create("FRAGB.BIN");
    for (off=0; off<131072UL; off+=512) {
        fill(off,512,0x5a); require(write(a,buffer+1,512)==512,"fragment A");
        fill(off,512,0xa5); require(write(b,buffer+1,512)==512,"fragment B");
    }
    close_ok(a); close_ok(b);
    verify("FRAGA.BIN",131072UL,0x5a);
    verify("FRAGB.BIN",131072UL,0xa5);
    require(chdir("..")==0,"parent directory");
    require(mkdir("EMPTY")==0,"mkdir empty");
    require(rmdir("EMPTY")==0,"rmdir");
    memset(&r,0,sizeof(r)); r.h.ah=0x0d; intdos(&r,&r);
    printf("PASS: FAT operations; %u boundary sizes; %lu checks\n",
           (unsigned)(sizeof(sizes)/sizeof(sizes[0])),checks);
    return 0;
}

/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <io.h>
#include <dos.h>
#include <sys/stat.h>
static unsigned char data[1024], got[1024];
static void require(int ok,const char *what)
{
    if (!ok) { printf("FAIL: %s\n",what); exit(1); }
}
static int __far disk_error(unsigned device,unsigned error,unsigned __far *header)
{
    (void)device; (void)error; (void)header;
    _hardretn(_HARDERR_FAIL);
    return _HARDERR_FAIL;
}
static int create(const char *name)
{
    int fd=open(name,O_CREAT|O_TRUNC|O_RDWR|O_BINARY,S_IREAD|S_IWRITE);
    require(fd>=0,"create"); return fd;
}
static unsigned char pattern(unsigned long off)
{
    return (unsigned char)((off*17UL+(off>>8))^0x5a);
}
static void full(void)
{
    unsigned long written=0,off;
    unsigned n,i;
    int fd=create("FULL.BIN"), count;
    memset(data,0xa5,sizeof(data));
    do {
        count=write(fd,data,sizeof(data));
        if (count>0) written+=(unsigned)count;
        require(written<=32768UL,"fixture left too much free space");
    } while (count==sizeof(data));
    require(written>0,"full-volume test must allocate before failing");
    require(close(fd)==0,"close short write");
    fd=open("FULL.BIN",O_RDONLY|O_BINARY); require(fd>=0,"reopen short write");
    require(filelength(fd)==(long)written,"short-write file length");
    for (off=0;off<written;off+=n) {
        n=(unsigned)(written-off>sizeof(got)?sizeof(got):written-off);
        require(read(fd,got,n)==n,"read short-write prefix");
        for (i=0;i<n;i++) require(got[i]==0xa5,"short-write prefix data");
    }
    require(read(fd,got,1)==0,"short-write EOF");
    require(close(fd)==0 && unlink("FULL.BIN")==0,"release full file");
    fd=create("RECOVER.BIN");
    require(write(fd,data,sizeof(data))==sizeof(data),"write after freeing clusters");
    require(lseek(fd,0,SEEK_SET)==0 && read(fd,got,sizeof(got))==sizeof(got),"recovery read");
    require(memcmp(data,got,sizeof(data))==0,"recovery data");
    require(close(fd)==0 && unlink("RECOVER.BIN")==0,"recovery cleanup");
    printf("PASS: full volume, short write, EOF and recovery; bytes=%lu\n",written);
}
static void high(void)
{
    unsigned i,j;
    unsigned long off;
    int fd=open("HIGH.BIN",O_RDONLY|O_BINARY); require(fd>=0,"open high-cluster file");
    for (i=0;i<256;i++) {
        off=((unsigned long)i*7919UL)%((1UL<<20)-513);
        require(lseek(fd,(long)off,SEEK_SET)==(long)off,"high-cluster seek");
        require(read(fd,got,513)==513,"high-cluster read");
        for (j=0;j<513;j++) require(got[j]==pattern(off+j),"high-cluster data");
    }
    require(lseek(fd,1L<<20,SEEK_SET)==(1L<<20) && read(fd,got,1)==0,"high-cluster EOF");
    require(close(fd)==0,"close high-cluster file");
    puts("PASS: high FAT32 clusters, forward/backward seeks and cross-sector data");
}
static void fault(int writing)
{
    int fd=open("BROKEN.BIN",(writing?O_RDWR:O_RDONLY)|O_BINARY),result,closed;
    require(fd>=0,"open fault target");
    _harderr(disk_error);
    memset(data,0xcc,512);
    result=writing?write(fd,data,512):read(fd,got,512);
    closed=close(fd);
    require(result<512 || closed!=0,"injected I/O error must reach application");
    /* A read may flush pending writes, so a persistently failed device
       need not accept another read. The host verifies the file's exact
       length/data and filesystem after shutdown, outside blkdebug. */
    printf("PASS: injected %s error returned to application\n",writing?"write":"read");
}
int main(int argc,char **argv)
{
    require(argc==2,"mode argument");
    if (!strcmp(argv[1],"full")) full();
    else if (!strcmp(argv[1],"high")) high();
    else if (!strcmp(argv[1],"readerror")) fault(0);
    else if (!strcmp(argv[1],"writeerror")) fault(1);
    else require(0,"unknown mode");
    return 0;
}

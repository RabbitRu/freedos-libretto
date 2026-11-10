#!/usr/bin/env python3
"""FAT16/FAT32 full-volume, high-cluster and real block-I/O error regressions."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import images

ROOT=Path(__file__).resolve().parents[2]
OFFSET=images.OFFSET

def geometry(disk):
    with disk.open('rb') as f:
        f.seek(OFFSET); b=f.read(512)
    bps=struct.unpack_from('<H',b,11)[0]; spc=b[13]
    reserved=struct.unpack_from('<H',b,14)[0]; copies=b[16]
    roots=struct.unpack_from('<H',b,17)[0]
    spf=struct.unpack_from('<H',b,22)[0] or struct.unpack_from('<I',b,36)[0]
    total=struct.unpack_from('<H',b,19)[0] or struct.unpack_from('<I',b,32)[0]
    root_sectors=(roots*32+bps-1)//bps
    fat=OFFSET+reserved*bps; root=fat+copies*spf*bps
    data=root+root_sectors*bps
    clusters=(total-reserved-copies*spf-root_sectors)//spc
    return dict(bps=bps,spc=spc,fat=fat,spf=spf,root=root,data=data,clusters=clusters,
                bits=16 if roots else 32,root_cluster=struct.unpack_from('<I',b,44)[0] if not roots else 0,
                root_bytes=roots*32)

def target(disk,short_name):
    g=geometry(disk)
    start=g['root'] if g['bits']==16 else g['data']+(g['root_cluster']-2)*g['bps']*g['spc']
    length=g['root_bytes'] if g['bits']==16 else g['bps']*g['spc']
    with disk.open('rb') as f:
        f.seek(start); entries=f.read(length)
    for off in range(0,len(entries),32):
        if entries[off:off+11]==short_name:
            low=struct.unpack_from('<H',entries,off+26)[0]
            high=struct.unpack_from('<H',entries,off+20)[0] if g['bits']==32 else 0
            cluster=low|(high<<16)
            return cluster,(g['data']+(cluster-2)*g['bps']*g['spc'])//512
    raise AssertionError('missing fixture directory entry')

def make_disk(payload,disk,mbr,bits):
    if bits==32:
        images.make_disk(payload,disk,mbr)
    else:
        entries=','.join(repr(str(p)) for p in sorted(payload.iterdir()) if p.is_file())
        images.run(['nasm',ROOT/'test/bootimg/bootimg.asm','-I'+str(ROOT/'test/lmacros')+'/',
                    '-D_MBR=1','-D_MBR_GAP_SIZE_SECTORS=2048','-D_BPE=16','-D_SPC=2',
                    '-D_SPI=32768','-D_SPF=64','-D_NUMRESERVED=1','-D_NUMROOT=512',
                    '-D_CHS_HEADS=16','-D_CHS_SECTORS=63','-D_UNIT=80h','-D_WARN_DEFAULT_OFF=1',
                    '-D_WARN_TOOMANYFAT=0','-D_WARN_ALIGNDATA=0',
                    '-D_BOOTPATCHFILE='+repr(str(ROOT/'boot/fat16com.bin')),
                    '-D_MBRPATCHFILE='+repr(str(mbr)),'-D_PAYLOADFILE='+entries,'-o',disk])
    g=geometry(disk)
    assert g['bits']==bits
    assert (4085<=g['clusters']<65525) if bits==16 else g['clusters']>=65525

def copy_file(disk,path,name):
    images.run(['mcopy','-i',str(disk)+'@@'+str(OFFSET),path,'::'+name])

def full_fixture(disk,tools):
    g=geometry(disk)
    with disk.open('rb') as f:
        f.seek(g['fat']); fat=f.read(g['spf']*g['bps'])
    code='<H' if g['bits']==16 else '<I'; width=g['bits']//8
    free=sum(struct.unpack_from(code,fat,i*width)[0]==0 for i in range(2,g['clusters']+2))
    filler=tools/'filler.bin'
    with filler.open('wb') as f: f.truncate((free-8)*g['spc']*g['bps'])
    copy_file(disk,filler,'BLOAT.BIN'); filler.unlink()

def fsck(disk,tools):
    volume=tools/'volume.img'
    with disk.open('rb') as f,volume.open('wb') as out:
        f.seek(OFFSET); shutil.copyfileobj(f,out)
    checked=subprocess.run(['fsck.fat','-n',str(volume)],capture_output=True,text=True)
    volume.unlink()
    assert checked.returncode==0,checked.stdout+checked.stderr
    return checked.stdout.strip()

def main():
    cpu=sys.argv[1]; assert cpu in ('486','pentium-mmx')
    package=ROOT/'_output'/('libretto-'+cpu+'-fat32')
    output=package/'edge-tests'; output.mkdir()
    tools=output/'tools'; tools.mkdir()
    env=dict(os.environ,LIBRETTO_CPU=cpu,LIBRETTO_RAM_MB='20')
    watcom=Path(env.get('WATCOM',str(ROOT/'_watcom')))
    env['PATH']=str(watcom/'binl64')+os.pathsep+env['PATH']
    images.run(['wcl','-zq','-bt=dos','-ms','-0','-os','-k4096','-I'+str(watcom/'h'),
                '-fe=FSEDGE.EXE',ROOT/'scripts/libretto/dos/fsedge.c'],cwd=tools,env=env)
    for name in ['mbr','poweroff']:
        images.run(['nasm','-f','bin',ROOT/f'scripts/libretto/dos/{name}.asm','-o',
                    tools/(name+'.bin' if name=='mbr' else 'POWEROFF.COM')])
    payload=tools/'payload'; payload.mkdir()
    for name in ['COMMAND.COM','HIMEMX.EXE']:
        shutil.copy2(ROOT/'_downloads/runtime-extracted'/name,payload/name)
    for name in ['FSEDGE.EXE','POWEROFF.COM']: shutil.copy2(tools/name,payload/name)
    shutil.copy2(package/'KERNEL.SYS',payload/'KERNEL.SYS')
    images.dos_text(payload/'FDCONFIG.SYS',images.config('xms'))
    pattern=lambda n:bytes(((i*17+(i>>8))^0x5a)&255 for i in range(n))
    (payload/'BROKEN.BIN').write_bytes(pattern(512))
    results=[]
    for bits in [16,32]:
        for mode in ['full','readerror','writeerror']+(['high'] if bits==32 else []):
            name=f'fat{bits}-{mode}'
            images.dos_text(payload/'AUTOEXEC.BAT','@ECHO OFF\nFSEDGE '+mode+' > EDGELOG.TXT\n'
                            'IF ERRORLEVEL 1 GOTO FAIL\nECHO PASS > RESULT.TXT\nPOWEROFF\n'
                            ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n')
            disk=tools/(name+'.img'); make_disk(payload,disk,tools/'mbr.bin',bits)
            if mode=='full': full_fixture(disk,tools)
            if mode=='high':
                pad=tools/'pad.bin'
                with pad.open('wb') as f: f.truncate(34*1024*1024)
                copy_file(disk,pad,'PAD.BIN'); pad.unlink()
                high=tools/'high.bin'; high.write_bytes(pattern(1<<20))
                copy_file(disk,high,'HIGH.BIN'); high.unlink()
                images.run(['mdel','-i',str(disk)+'@@'+str(OFFSET),'::PAD.BIN'])
                cluster,_=target(disk,b'HIGH    BIN')
                assert cluster>65535,'fixture must exercise full 32-bit cluster numbers'
            drive=str(disk)
            if mode in ['readerror','writeerror']:
                _,sector=target(disk,b'BROKEN  BIN')
                fault=tools/(name+'.conf')
                fault.write_text('[inject-error]\nevent = "'+('read_aio' if mode=='readerror' else 'write_aio')+
                                 '"\nerrno = "5"\nsector = "'+str(sector)+'"\nonce = "off"\n')
                drive=f'blkdebug:{fault}:{disk}'
            log=output/(name+'.qemu.log')
            command=[ROOT/'scripts/libretto/qemu-target.sh','-drive',f'file={drive},format=raw,if=ide',
                     '-boot','c','-display','none','-no-reboot']
            try:
                with log.open('wb') as f:
                    images.run(command,env=env,timeout=120,stdout=f,stderr=subprocess.STDOUT)
                text=images.mread(disk,'EDGELOG.TXT').decode('ascii')
                (output/(name+'.txt')).write_text(text)
                assert images.mread(disk,'RESULT.TXT').strip()==b'PASS',text
                if mode in ['readerror','writeerror']:
                    assert images.mread(disk,'BROKEN.BIN')==pattern(512),'injected failure changed target data'
                checked=fsck(disk,tools)
                results.append(dict(fat=bits,mode=mode,status='pass',guest=text.strip(),fsck=checked))
                print('EDGE_PASS '+json.dumps(results[-1]),flush=True)
            except Exception:
                print(log.read_text(errors='replace')[-4000:],flush=True)
                for name in ['EDGELOG.TXT','RESULT.TXT']:
                    try: print(name+': '+images.mread(disk,name).decode('ascii',errors='replace'),flush=True)
                    except subprocess.CalledProcessError: pass
                raise
            disk.unlink()
    (output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    shutil.rmtree(tools)

if __name__=='__main__': main()

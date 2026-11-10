#!/usr/bin/env python3
"""Check checkpoint invalidation on both control and candidate kernels."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import edges
import images
ROOT=images.ROOT
LENGTH=256*1024

def pattern(n,salt=1):
    return bytes((i*17+(i>>8)+(i>>16)*37+salt*53)&255 for i in range(n))

def chain(disk,name):
    g=edges.geometry(disk); first,_=edges.target(disk,name)
    result=[]; c=first
    with disk.open('rb') as f:
        while c < (0xfff8 if g['bits']==16 else 0x0ffffff8):
            assert c>=2 and c not in result
            result.append(c)
            f.seek(g['fat']+c*(g['bits']//8))
            c=struct.unpack('<H' if g['bits']==16 else '<I',f.read(g['bits']//8))[0]
    return g,result

def raw_fixture(disk,tools):
    for name,salt in [('TARGET',1),('OTHER',4)]:
        p=tools/(name+'.BIN'); p.write_bytes(pattern(LENGTH,salt)); edges.copy_file(disk,p,p.name)
    p=tools/'RAWCFG.BIN'; p.write_bytes(bytes(2+4*516)); edges.copy_file(disk,p,p.name)
    g,a=chain(disk,b'TARGET  BIN'); _,b=chain(disk,b'OTHER   BIN')
    sectors={}; order=[]
    with disk.open('rb') as f:
        for copy in range(2):
            for source,dest in [(a[0],b[1]),(b[0],a[1])]:
                absolute=g['fat']+copy*g['spf']*512+(source*4//512)*512
                if absolute not in sectors:
                    f.seek(absolute); sectors[absolute]=bytearray(f.read(512))
                struct.pack_into('<I',sectors[absolute],source*4%512,dest)
                order.append(absolute)
    config=struct.pack('<H',4)+b''.join(struct.pack('<I',(s-images.OFFSET)//512)+sectors[s] for s in order)
    assert len(config)==p.stat().st_size
    _,blocks=chain(disk,b'RAWCFG  BIN')
    # Update payload in place, preserving FAT allocation captured above.
    with disk.open('r+b') as f:
        for i,c in enumerate(blocks):
            f.seek(g['data']+(c-2)*512)
            f.write(config[i*512:(i+1)*512])
    assert images.mread(disk,'RAWCFG.BIN')==config

def floppy(tools,salt):
    disk=tools/f'floppy-{salt}.img'
    with disk.open('wb') as f: f.truncate(1440*1024)
    images.run(['mkfs.fat','-F','12',disk])
    src=tools/'floppy-target.bin'; src.write_bytes(pattern(LENGTH,salt))
    images.run(['mcopy','-i',disk,src,'::TARGET.BIN'])
    if salt==6:
        # Keep the same first cluster but reverse the rest of the chain.
        # Both media have the same geometry, start cluster and file length.
        d=bytearray(disk.read_bytes()); bps=512; spc=d[13]
        reserved=struct.unpack_from('<H',d,14)[0]; copies=d[16]
        roots=struct.unpack_from('<H',d,17)[0]; spf=struct.unpack_from('<H',d,22)[0]
        fat=reserved*bps; root=fat+copies*spf*bps; data=root+((roots*32+511)//512)*512
        first=struct.unpack_from('<H',d,root+26)[0]
        def get(c):
            v=struct.unpack_from('<H',d,fat+c*3//2)[0]
            return (v>>4 if c&1 else v)&0xfff
        blocks=[]; c=first
        while c<0xff8: blocks.append(c); c=get(c)
        assert len(blocks)>8
        altered=blocks[:1]+blocks[:0:-1]; content=src.read_bytes(); size=spc*bps
        for i,c in enumerate(altered):
            d[data+(c-2)*size:data+(c-1)*size]=content[i*size:(i+1)*size]
            nxt=altered[i+1] if i+1<len(altered) else 0xfff
            for copy in range(copies):
                off=fat+copy*spf*bps+c*3//2; old=struct.unpack_from('<H',d,off)[0]
                struct.pack_into('<H',d,off,(old&0x000f)|(nxt<<4) if c&1 else (old&0xf000)|nxt)
        disk.write_bytes(d)
    got=subprocess.check_output(['mtype','-i',str(disk),'::TARGET.BIN'])
    assert got==pattern(LENGTH,salt)
    images.run(['fsck.fat','-n',disk])
    return disk

def swap_run(command,env,log,tools,media):
    # QMP over pipes also works in environments where sockets are unavailable.
    debug=tools/'debug.txt'; debug.unlink(missing_ok=True)
    command += ['-drive',f'file={media[0]},format=raw,if=floppy,id=swap',
                '-qmp','stdio','-debugcon',f'file:{debug}']
    with log.open('wb') as stream:
        proc=subprocess.Popen(list(map(str,command)),env=env,stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,stderr=stream)
        try:
            limit=time.monotonic()+90
            def receive():
                while True:
                    line=proc.stdout.readline()
                    assert line,'QMP closed unexpectedly'
                    obj=json.loads(line)
                    if 'return' in obj or 'error' in obj: return obj
            def call(cmd,args=None):
                proc.stdin.write((json.dumps(dict(execute=cmd,**({'arguments':args} if args else {})))+'\n').encode())
                proc.stdin.flush()
                answer=receive(); assert 'error' not in answer,answer
            json.loads(proc.stdout.readline()); call('qmp_capabilities')
            while not debug.exists() or b'SWAP' not in debug.read_bytes():
                assert proc.poll() is None,'QEMU exited before swap handshake'
                assert time.monotonic()<limit,'guest swap handshake timeout'
                time.sleep(.05)
            call('blockdev-change-medium',dict(device='swap',filename=str(media[1]),format='raw'))
            call('human-monitor-command',{'command-line':'sendkey ret'})
            assert proc.wait(timeout=90)==0
        finally:
            if proc.poll() is None: proc.kill(); proc.wait()
            proc.stdin.close(); proc.stdout.close()

def main():
    cpu=sys.argv[1]; assert cpu in ('486','pentium-mmx')
    package=ROOT/'_output'/f'libretto-{cpu}-fat32'
    output=package/'chain-tests'; output.mkdir(exist_ok=True)
    tools=output/'tools'; tools.mkdir(exist_ok=True)
    env=dict(os.environ,WATCOM=str(ROOT/'_watcom'),LIBRETTO_CPU=cpu,LIBRETTO_RAM_MB='20')
    env['PATH']=str(ROOT/'_watcom/binl64')+os.pathsep+env['PATH']
    images.run(['wcl','-zq','-bt=dos','-ms','-0','-os','-k4096','-I'+str(ROOT/'_watcom/h'),
                '-fe=CHAIN.EXE',ROOT/'scripts/libretto/dos/chainverify.c'],cwd=tools,env=env)
    for name in ['mbr','poweroff']:
        images.run(['nasm','-f','bin',ROOT/f'scripts/libretto/dos/{name}.asm','-o',
                    tools/(name+'.bin' if name=='mbr' else 'POWEROFF.COM')])
    payload=tools/'payload'; payload.mkdir(exist_ok=True)
    for name in ['COMMAND.COM','HIMEMX.EXE']: shutil.copy2(ROOT/'_downloads/runtime-extracted'/name,payload/name)
    for name in ['CHAIN.EXE','POWEROFF.COM']: shutil.copy2(tools/name,payload/name)
    images.dos_text(payload/'FDCONFIG.SYS',images.config('xms'))
    media=[floppy(tools,salt) for salt in (1,6)]
    results=[]
    variants=['control','candidate']
    if os.environ.get('LIBRETTO_CHAIN_VARIANT'): variants=[os.environ['LIBRETTO_CHAIN_VARIANT']]
    for variant in variants:
        kernel=package/'comparison/control.sys' if variant=='control' else package/'KERNEL.SYS'
        shutil.copy2(kernel,payload/'KERNEL.SYS')
        for bits in (16,32):
            for mode in ['handles','resize','reuse']+(['rawfat','media'] if bits==32 else []):
                if os.environ.get('LIBRETTO_CHAIN_MODE') and mode!=os.environ['LIBRETTO_CHAIN_MODE']: continue
                name=f'{variant}-fat{bits}-{mode}'
                images.dos_text(payload/'AUTOEXEC.BAT','@ECHO OFF\nCHAIN '+mode+' > CHAINLOG.TXT\n'
                    'IF ERRORLEVEL 1 GOTO FAIL\nECHO PASS > RESULT.TXT\nPOWEROFF\n'
                    ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n')
                disk=tools/(name+'.img'); edges.make_disk(payload,disk,tools/'mbr.bin',bits)
                if mode=='rawfat': raw_fixture(disk,tools)
                log=output/(name+'.qemu.log')
                command=[ROOT/'scripts/libretto/qemu-target.sh','-drive',f'file={disk},format=raw,if=ide',
                         '-boot','c','-display','none','-no-reboot']
                try:
                    if mode=='media': swap_run(command,env,log,tools,media)
                    else:
                        with log.open('wb') as f: images.run(command,env=env,timeout=120,stdout=f,stderr=subprocess.STDOUT)
                    text=images.mread(disk,'CHAINLOG.TXT').decode('ascii')
                    (output/(name+'.txt')).write_text(text)
                    assert images.mread(disk,'RESULT.TXT').strip()==b'PASS',text
                    if mode!='media':
                        expected=pattern(LENGTH,dict(handles=1,resize=3,reuse=8,rawfat=4)[mode])
                        if mode=='rawfat': expected=pattern(512,1)+expected[512:]
                        assert images.mread(disk,'TARGET.BIN')==expected,'independent target data'
                        if mode=='rawfat':
                            assert images.mread(disk,'OTHER.BIN')==pattern(512,4)+pattern(LENGTH,1)[512:]
                    checked=edges.fsck(disk,tools)
                    results.append(dict(variant=variant,fat=bits,mode=mode,status='pass',guest=text.strip(),fsck=checked))
                    print('CHAIN_PASS '+json.dumps(results[-1]),flush=True)
                except Exception:
                    print(log.read_text(errors='replace')[-4000:],flush=True)
                    for f in ['CHAINLOG.TXT','RESULT.TXT']:
                        try: print(f+': '+images.mread(disk,f).decode('ascii',errors='replace'),flush=True)
                        except subprocess.CalledProcessError: pass
                    raise
                disk.unlink()
    (output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    shutil.rmtree(tools)

if __name__=='__main__': main()

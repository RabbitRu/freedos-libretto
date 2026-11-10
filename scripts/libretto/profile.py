#!/usr/bin/env python3
"""Separate diagnostic kernel: operation counts, never release speed claims."""
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import images

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ['map_calls','chain_steps','backward_seeks','fat_reads','fat_writes',
          'buffer_probes','buffer_hits','buffer_misses','disk_calls','seek_hits','seek_saves']

def main():
    cpu = sys.argv[1]
    assert cpu in ('486','pentium-mmx')
    output = ROOT/'_output'/('profile-'+cpu)
    output.mkdir(parents=True,exist_ok=True)
    tools = output/'tools'; tools.mkdir(exist_ok=True)
    env = dict(os.environ,WATCOM=str(ROOT/'_watcom'),LIBRETTO_PROFILE='1',
               LIBRETTO_TUNE='4' if cpu=='486' else '5',LIBRETTO_CPU=cpu,LIBRETTO_RAM_MB='20')
    env['PATH'] = str(ROOT/'_watcom/binl64')+os.pathsep+env['PATH']
    flags = ['COMPILER=owlinux','XCPU=386','XFAT=32','XUPX=','RM=rm -f']
    with (output/'build.log').open('wb') as log:
        for target in ['clobber','all']:
            try:
                images.run(['make',target]+flags,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                log.flush()
                print((output/'build.log').read_text(errors='replace')[-6000:],flush=True)
                raise
    images.run(['python3',ROOT/'scripts/libretto/runtime.py',ROOT/'_downloads/runtime-extracted'])
    images.run(['gcc','-shared','-fPIC','-fvisibility=hidden','-O2','-Wall','-Wextra','-Werror',
                ROOT/'scripts/libretto/qemu/instruction_count.c','-o',tools/'counter.so'])
    images.run(['wcl','-zq','-bt=dos','-ms','-0','-os','-k4096','-I'+str(ROOT/'_watcom/h'),
                '-fe=DOSBENCH.EXE',ROOT/'scripts/libretto/dos/dosbench.c'],cwd=tools,env=env)
    for name in ['mbr','poweroff']:
        images.run(['nasm','-f','bin',ROOT/f'scripts/libretto/dos/{name}.asm','-o',
                    tools/(name+'.bin' if name=='mbr' else 'POWEROFF.COM')])
    payload = tools/'payload'; payload.mkdir()
    shutil.copy2(ROOT/'bin/kwc38632.sys',payload/'KERNEL.SYS')
    for name in ['COMMAND.COM','HIMEMX.EXE']:
        shutil.copy2(ROOT/'_downloads/runtime-extracted'/name,payload/name)
    for name in ['DOSBENCH.EXE','POWEROFF.COM']: shutil.copy2(tools/name,payload/name)
    images.dos_text(payload/'FDCONFIG.SYS',images.config('xms'))
    images.dos_text(payload/'AUTOEXEC.BAT','@ECHO OFF\nDOSBENCH 1 > BENCH.CSV\n'
                    'IF ERRORLEVEL 1 GOTO FAIL\nECHO PASS > RESULT.TXT\nPOWEROFF\n'
                    ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n')
    disk = tools/'profile.img'
    images.make_disk(payload,disk,tools/'mbr.bin')
    counts = output/'counts.csv'
    command = [ROOT/'scripts/libretto/qemu-target.sh','-accel','tcg,thread=single',
               '-smp','1,maxcpus=1','-icount','shift=3,align=off,sleep=off',
               '-rtc','base=2026-01-01T00:00:00,clock=vm',
               '-plugin',f'file={tools}/counter.so,out={counts}',
               '-drive',f'file={disk},format=raw,if=ide','-boot','c','-display','none','-no-reboot']
    try:
        with (output/'qemu.log').open('wb') as log:
            images.run(command,cwd=ROOT,env=env,timeout=420,stdout=log,stderr=subprocess.STDOUT)
        assert images.mread(disk,'RESULT.TXT').strip()==b'PASS'
        dos = images.mread(disk,'BENCH.CSV').decode('ascii')
        (output/'dos.csv').write_text(dos)
        rows = list(csv.DictReader(io.StringIO(dos)))
        with counts.open() as f: samples = list(csv.DictReader(f))
        assert len(rows)==len(samples)==4
        combined = []
        for i,(row,sample) in enumerate(zip(rows,samples)):
            assert int(sample['marker_errors'])==0 and int(sample['interval'])==i+1
            values = {key:int(sample[key]) for key in EVENTS}
            assert values['map_calls']>0 and values['fat_reads']>0 and values['buffer_probes']>0
            combined.append(dict(scenario=row['scenario'],**values))
        report = dict(cpu=cpu,commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                      diagnostic_only=True,ram_mib=20,memory_profile='xms',workloads=combined)
        (output/'profile.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PROFILE_REPORT '+json.dumps(report),flush=True)
        shutil.rmtree(tools)
    except Exception:
        print((output/'qemu.log').read_text(errors='replace')[-4000:],flush=True)
        raise

if __name__=='__main__': main()

#!/usr/bin/env python3
"""Paired QEMU instruction-count experiments, not real CPU timings."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import images

ROOT=Path(__file__).resolve().parents[2]
BASELINE='5f17969cd603eeef159f8706e63ee7631ecd5419'
ORDER=['control','candidate','candidate','control']
REPEATS=5
SCENARIOS=['write_1m_flush','repeated_read_16m','random_read_1m','small_files_100']

def run(args,**kw):
    print('+',' '.join(map(str,args)),flush=True)
    return subprocess.run(list(map(str,args)),check=True,**kw)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def build_control(cpu,output,env):
    work=ROOT/'_output'/('control-source-'+cpu)
    run(['git','fetch','--depth=1','origin',BASELINE])
    run(['git','worktree','add','--detach',work,BASELINE])
    try:
        run(['git','-C',work,'submodule','update','--init','country'])
        with (output/'control-build.log').open('wb') as log:
            flags=['COMPILER=owlinux','XCPU=386','XFAT=32','XUPX=','RM=rm -f']
            run(['make','clobber']+flags,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT)
            run(['make','all']+flags,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT)
        shutil.copy2(work/'bin/kwc38632.sys',output/'control.sys')
    finally:
        run(['git','worktree','remove','--force',work])

def main():
    cpu=sys.argv[1]
    assert cpu in ('486','pentium-mmx')
    package=ROOT/'_output'/('libretto-'+cpu+'-fat32')
    output=package/'comparison'; output.mkdir(parents=True,exist_ok=True)
    tools=output/'tools'; tools.mkdir(exist_ok=True)
    env=dict(os.environ,WATCOM=str(ROOT/'_watcom'),LIBRETTO_TUNE='4' if cpu=='486' else '5',
             LIBRETTO_CPU=cpu,LIBRETTO_RAM_MB='20')
    env['PATH']=str(ROOT/'_watcom/binl64')+os.pathsep+env['PATH']
    version=subprocess.check_output(['qemu-system-i386','--version'],text=True).splitlines()[0]
    assert 'version 8.2.' in version,'Plugin header requires QEMU 8.2'
    run(['gcc','-shared','-fPIC','-fvisibility=hidden','-O2','-Wall','-Wextra','-Werror',
         ROOT/'scripts/libretto/qemu/instruction_count.c','-o',tools/'counter.so'])
    build_control(cpu,output,env)
    shutil.copy2(package/'KERNEL.SYS',output/'candidate.sys')
    run(['wcl','-zq','-bt=dos','-ms','-0','-os','-k4096','-I'+str(ROOT/'_watcom/h'),
         '-fe=DOSBENCH.EXE',ROOT/'scripts/libretto/dos/dosbench.c'],cwd=tools,env=env)
    for name in ['memstat','poweroff','mbr']:
        run(['nasm','-f','bin',ROOT/f'scripts/libretto/dos/{name}.asm','-o',
             tools/(name+'.bin' if name=='mbr' else name.upper()+'.COM')])
    payload=tools/'payload'; payload.mkdir()
    runtime=ROOT/'_downloads/runtime-extracted'
    for name in ['COMMAND.COM','HIMEMX.EXE']: shutil.copy2(runtime/name,payload/name)
    for name in ['MEMSTAT.COM','POWEROFF.COM','DOSBENCH.EXE']: shutil.copy2(tools/name,payload/name)
    images.dos_text(payload/'FDCONFIG.SYS',images.config('xms'))
    images.dos_text(payload/'AUTOEXEC.BAT',
        '@ECHO OFF\nPATH=C:\\\nMEMSTAT > MEMORY.TXT\nDOSBENCH '+str(REPEATS)+' > BENCH.CSV\n'
        'IF ERRORLEVEL 1 GOTO FAIL\nECHO PASS > RESULT.TXT\nPOWEROFF\nGOTO END\n'
        ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n:END\n')
    templates={}
    for v in ['control','candidate']:
        shutil.copy2(output/(v+'.sys'),payload/'KERNEL.SYS')
        templates[v]=tools/(v+'.img')
        images.make_disk(payload,templates[v],tools/'mbr.bin')
    identical=sha(output/'control.sys')==sha(output/'candidate.sys')
    if identical:
        assert sha(templates['control'])==sha(templates['candidate']),'Calibration disk images differ'
    data=[]; boots={'control':0,'candidate':0}
    for variant in ORDER:
        batch=boots[variant]; boots[variant]+=1
        name=variant+'-'+str(batch)
        disk=tools/(name+'.img'); shutil.copy2(templates[variant],disk)
        count=output/(name+'-instructions.csv'); log=output/(name+'-qemu.log')
        command=[ROOT/'scripts/libretto/qemu-target.sh','-accel','tcg,thread=single',
                 '-smp','1,maxcpus=1','-icount','shift=3,align=off,sleep=off',
                 '-rtc','base=2026-01-01T00:00:00,clock=vm',
                 '-plugin','file='+str(tools/'counter.so')+',out='+str(count),
                 '-drive','file='+str(disk)+',format=raw,if=ide',
                 '-boot','c','-display','none','-no-reboot']
        started=time.monotonic()
        try:
            with log.open('wb') as stream:
                run(command,env=env,timeout=int(os.environ.get("LIBRETTO_COMPARE_TIMEOUT","420")),stdout=stream,stderr=subprocess.STDOUT)
            assert images.mread(disk,'RESULT.TXT').strip()==b'PASS'
            memory=dict((k,int(v)) for k,v in (line.split('=',1) for line in images.mread(disk,'MEMORY.TXT').decode('ascii').splitlines()))
            assert memory['xms_present']==1 and memory['dos_in_hma']==1
            text=images.mread(disk,'BENCH.CSV').decode('ascii')
            (output/(name+'-dos.csv')).write_text(text)
            rows=list(csv.DictReader(io.StringIO(text)))
            with count.open() as stream: counters=list(csv.DictReader(stream))
            assert len(rows)==len(counters)==REPEATS*4,'Missing measurement regions'
            for i,(row,counter) in enumerate(zip(rows,counters)):
                assert row['scenario']==SCENARIOS[i%4] and int(row['run'])==i//4+1
                assert int(counter['interval'])==i+1 and int(counter['marker_errors'])==0
                total=int(counter['guest_instructions']); non_rom=int(counter['non_rom_instructions'])
                assert total>=non_rom>0
                data.append(dict(variant=variant,batch=batch,run=int(row['run']),scenario=row['scenario'],
                                 guest_instructions=total,non_rom_instructions=non_rom,bios_ticks=int(row['bios_ticks'])))
            print('AB_BOOT '+json.dumps(dict(variant=variant,batch=batch,samples=len(rows),
                       host_seconds=time.monotonic()-started,memory=memory)),flush=True)
        except Exception:
            print(log.read_text(errors='replace')[-4000:],flush=True)
            for fn in ['MEMORY.TXT','BENCH.CSV','RESULT.TXT']:
                try: print(fn+': '+images.mread(disk,fn).decode('ascii',errors='replace'),flush=True)
                except subprocess.CalledProcessError: pass
            raise
        disk.unlink()
    summaries=[]
    for scenario in SCENARIOS:
        selected={v:[r for r in data if r['variant']==v and r['scenario']==scenario] for v in ('control','candidate')}
        assert all(len(r)==10 for r in selected.values())
        summary=dict(scenario=scenario,samples_per_variant=10)
        for metric in ['guest_instructions','non_rom_instructions','bios_ticks']:
            a=[r[metric] for r in selected['control']]; b=[r[metric] for r in selected['candidate']]
            ratios=[(y/x-1)*100 for x,y in zip(a,b) if x]
            summary[metric]=dict(control_median=statistics.median(a),candidate_median=statistics.median(b),
                control_min=min(a),control_max=max(a),candidate_min=min(b),candidate_max=max(b),
                paired_change_percent_median=statistics.median(ratios) if ratios else None)
        summaries.append(summary)
    neutral=max(abs(r['non_rom_instructions']['paired_change_percent_median']) for r in summaries)
    report=dict(baseline_commit=BASELINE,candidate_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
         cpu=cpu,ram_mib=20,memory_profile='xms',qemu_version=version,icount='shift=3,align=off,sleep=off',order=ORDER,
         control_kernel_sha256=sha(output/'control.sys'),candidate_kernel_sha256=sha(output/'candidate.sys'),
         kernel_bytes_identical=identical,calibration=('pass' if neutral<=1 else 'noisy') if identical else 'not_applicable',
         max_identical_kernel_median_change_percent=neutral if identical else None,summaries=summaries,raw=data,
         limitations=['Instruction counts are not CPU cycles or Libretto speed.',
                      'non_rom excludes 0xA0000..0xFFFFF; it is not a kernel-only counter.',
                      'BIOS ticks use the artificial icount clock; host wall time is diagnostic only.',
                      'Performance acceptance requires gains above measured calibration noise.'])
    (output/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# QEMU comparison','',f'CPU: {cpu}; RAM: 20 MiB; XMS/HMA.',f'Baseline: {BASELINE}',
           f'Identical kernels: {identical}; calibration: {report["calibration"]}','',
           '| Workload | Samples/variant | Control non-ROM median | Candidate non-ROM median | Paired change |',
           '| --- | ---: | ---: | ---: | ---: |']
    for row in summaries:
        m=row['non_rom_instructions']
        lines.append(f'| {row["scenario"]} | 10 | {m["control_median"]} | {m["candidate_median"]} | {m["paired_change_percent_median"]:.4f}% |')
    lines+=['','Executed guest instructions are not real CPU timings. Identical kernels calibrate the method, not an optimization.']
    (output/'comparison.md').write_text('\n'.join(lines)+'\n')
    print('AB_SUMMARY '+json.dumps({k:v for k,v in report.items() if k!='raw'}),flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f: f.write('\n'.join(lines)+'\n')
    shutil.rmtree(tools)

if __name__=='__main__': main()

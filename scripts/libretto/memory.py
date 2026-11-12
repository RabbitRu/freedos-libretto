#!/usr/bin/env python3
"""Exercise the actual memory assembly, then compare identical DOS harnesses.

REP calibration is retained alongside the samples: these are QEMU instruction
counts, not 486/Pentium cycles or a prediction of native throughput.
"""
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
import images

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '28dc3c7f0ce5f29440905bc54af37591f8db8b67'


def main():
    cpu = sys.argv[1]
    assert cpu in ('486', 'pentium-mmx')
    package = ROOT/'_output'/f'libretto-{cpu}-fat32'
    output = package/'memory'; output.mkdir(parents=True, exist_ok=True)
    tools = output/'tools'; tools.mkdir(exist_ok=True)
    env = dict(os.environ, WATCOM=str(ROOT/'_watcom'), LIBRETTO_CPU=cpu, LIBRETTO_RAM_MB='20')
    env['PATH'] = str(ROOT/'_watcom/binl64')+os.pathsep+env['PATH']
    version = subprocess.check_output(['qemu-system-i386', '--version'], text=True).splitlines()[0]
    assert 'version 8.2.' in version, 'Counter header requires QEMU 8.2'
    run = images.run
    run(['gcc', '-shared', '-fPIC', '-fvisibility=hidden', '-O2', '-Wall', '-Wextra', '-Werror',
         ROOT/'scripts/libretto/qemu/instruction_count.c', '-o', tools/'counter.so'])
    run(['nasm', '-f', 'obj', ROOT/'scripts/libretto/dos/memcheck.asm', '-o', tools/'check.obj'])
    run(['git', 'fetch', '--depth=1', 'origin', BASELINE])
    control = subprocess.check_output(['git', 'show', BASELINE+':kernel/asmsupt.asm'], cwd=ROOT)
    (tools/'control.asm').write_bytes(control)
    candidate = (ROOT/'kernel/asmsupt.asm').read_bytes()
    (tools/'candidate.asm').write_bytes(candidate)
    candidate_commit = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    for variant, source in [('REF', tools/'control.asm'), ('NEW', tools/'candidate.asm')]:
        obj = tools/(variant+'.obj')
        run(['nasm', '-f', 'obj', '-Dowlinux', '-DXCPU=386', '-I'+str(ROOT/'hdr')+'/',
             '-I'+str(ROOT/'kernel')+'/', source, '-o', obj])
        for program, prefix in [('memcheck', 'CHECK'), ('membench', 'BENCH')]:
            cmd = ['wcl', '-zq', '-bt=dos', '-ms', '-0', '-os', '-wx', '-we', '-k4096',
                   '-I'+str(ROOT/'_watcom/h'), '-fe='+prefix+variant+'.EXE',
                   ROOT/f'scripts/libretto/dos/{program}.c', obj]
            if program == 'memcheck': cmd.append(tools/'check.obj')
            run(cmd, cwd=tools, env=env)
    for name in ['mbr', 'poweroff', 'repcal']:
        run(['nasm', '-f', 'bin', ROOT/f'scripts/libretto/dos/{name}.asm', '-o',
             tools/(name+'.bin' if name == 'mbr' else name.upper()+'.COM')])
    payload = tools/'payload'; payload.mkdir(exist_ok=True)
    for name in ['COMMAND.COM', 'HIMEMX.EXE']:
        shutil.copy2(ROOT/'_downloads/runtime-extracted'/name, payload/name)
    shutil.copy2(package/'KERNEL.SYS', payload/'KERNEL.SYS')
    for prefix in ['CHECK', 'BENCH']:
        for variant in ['REF', 'NEW']: shutil.copy2(tools/(prefix+variant+'.EXE'), payload)
    for name in ['POWEROFF.COM', 'REPCAL.COM']: shutil.copy2(tools/name, payload/name)
    images.dos_text(payload/'FDCONFIG.SYS', images.config('xms'))
    reports = {}
    for phase, batch in [
        ('correctness', 'CHECKREF > CHECKREF.TXT\nIF ERRORLEVEL 1 GOTO FAIL\n'
                        'CHECKNEW > CHECKNEW.TXT\nIF ERRORLEVEL 1 GOTO FAIL\n'),
        ('benchmark', 'REPCAL\nIF ERRORLEVEL 1 GOTO FAIL\n'
                      'BENCHREF > BENCHREF.CSV\nIF ERRORLEVEL 1 GOTO FAIL\n'
                      'BENCHNEW > BENCHNEW.CSV\nIF ERRORLEVEL 1 GOTO FAIL\n')]:
        images.dos_text(payload/'AUTOEXEC.BAT', '@ECHO OFF\n'+batch+
                        'ECHO PASS > RESULT.TXT\nPOWEROFF\nGOTO END\n'
                        ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n:END\n')
        disk = tools/(phase+'.img')
        images.make_disk(payload, disk, tools/'mbr.bin')
        cmd = [ROOT/'scripts/libretto/qemu-target.sh', '-accel', 'tcg,thread=single',
               '-smp', '1,maxcpus=1', '-icount', 'shift=3,align=off,sleep=off',
               '-rtc', 'base=2026-01-01T00:00:00,clock=vm', '-drive',
               f'file={disk},format=raw,if=ide', '-boot', 'c', '-display', 'none', '-no-reboot']
        if phase == 'benchmark': cmd += ['-plugin', f'file={tools}/counter.so,out={output}/counts.csv']
        try:
            with (output/(phase+'.log')).open('wb') as log:
                run(cmd, env=env, timeout=600, stdout=log, stderr=subprocess.STDOUT)
            for name in (['CHECKREF.TXT', 'CHECKNEW.TXT'] if phase == 'correctness' else
                         ['BENCHREF.CSV', 'BENCHNEW.CSV']):
                text = images.mread(disk, name).decode('ascii')
                (output/name.lower()).write_text(text)
                reports[name] = text
            assert images.mread(disk, 'RESULT.TXT').strip() == b'PASS'
            if phase == 'correctness':
                assert all(v.startswith('PASS cases=') for v in reports.values()), reports
                print('MEMORY_CHECK '+json.dumps(reports), flush=True)
        except Exception:
            print((output/(phase+'.log')).read_text(errors='replace')[-4000:], flush=True)
            for name in ['CHECKREF.TXT', 'CHECKNEW.TXT', 'RESULT.TXT']:
                try: print(name, images.mread(disk, name).decode('ascii', errors='replace'), flush=True)
                except subprocess.CalledProcessError: pass
            raise
        disk.unlink()
    with (output/'counts.csv').open() as f: counts = list(csv.DictReader(f))
    assert all(int(r['marker_errors']) == 0 and int(r['interval']) == i+1 for i, r in enumerate(counts))
    calibration = [dict(operation=op, iterations=n, **counts[i*4+j])
                   for i, op in enumerate(['movsb', 'movsw', 'movsd'])
                   for j, n in enumerate([0, 1, 64, 1024])]
    assert all(int(r['non_rom_instructions']) == r['iterations']+2 for r in calibration), calibration
    rows = []
    cursor = 12
    for variant in ['REF', 'NEW']:
        dos = list(csv.DictReader(io.StringIO(reports['BENCH'+variant+'.CSV'])))
        for r in dos:
            rows.append(dict(variant=variant, **{k:int(v) for k,v in r.items()},
                             non_rom_instructions=int(counts[cursor]['non_rom_instructions'])))
            cursor += 1
    assert cursor == len(counts)
    summaries = []
    for key in sorted({(r['op'], r['bytes'], r['dest_alignment'], r['source_alignment']) for r in rows}):
        samples = {v:[r['non_rom_instructions'] for r in rows if r['variant']==v and
                      (r['op'], r['bytes'], r['dest_alignment'], r['source_alignment'])==key] for v in ['REF','NEW']}
        assert all(len(s)==3 for s in samples.values())
        a,b = (statistics.median(samples[v]) for v in ['REF','NEW'])
        summaries.append(dict(op=key[0], bytes=key[1], dest_alignment=key[2], source_alignment=key[3], control=a, candidate=b,
                              change_percent=(b/a-1)*100))
    report = dict(cpu=cpu, baseline_commit=BASELINE, qemu_version=version,
                  candidate_commit=candidate_commit,
                  candidate_assembly_sha256=hashlib.sha256(candidate).hexdigest(),
                  correctness={k:v for k,v in reports.items() if k.endswith('.TXT')},
                  rep_calibration=calibration, summaries=summaries, raw=rows,
                  limitations=['QEMU REP accounting is calibrated separately; instruction counts are not CPU cycles.',
                               'Microbenchmarks include caller dispatch and loop overhead.'])
    (output/'memory.json').write_text(json.dumps(report,indent=2)+'\n')
    print('MEMORY_REPORT '+json.dumps({k:v for k,v in report.items() if k not in ('raw','summaries')}),flush=True)
    shutil.rmtree(tools)


if __name__ == '__main__': main()

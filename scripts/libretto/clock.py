#!/usr/bin/env python3
"""Check actual DOS clocks/calendar and compare fixed-cache kernel services."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import images
import compare

BASELINE = 'a961f142a1fc2d5554b7eed4b871c952cd5e6beb'
SCENARIOS = ['time_hit', 'time_miss', 'date_1980', 'date_2026', 'date_2099', 'mixed']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host_check(output):
    root = images.ROOT
    sources = {name: root / 'kernel' / name for name in ['systime.c', 'sysclk.c']}
    systime = sources['systime.c'].read_text()
    sysclk = sources['sysclk.c'].read_text()
    commands = '\n'.join(re.findall(
        r'^#define\s+(?:C_\w+|E_LENGTH|E_FAILURE)\s+[^\n]+',
        (root / 'hdr/device.h').read_text(), re.M))
    (output / 'clock-under-test.h').write_text(commands + '\n' +
        systime[systime.index('const UWORD days'):] +
        sysclk[sysclk.index('UWORD ASM DaysSinceEpoch'):])
    binary = output / 'host-check'
    images.run(['gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-function', '-fsanitize=address,undefined',
                '-I' + str(output), root / 'scripts/libretto/clock_host.c', '-o', binary])
    checked = subprocess.run([str(binary)], env=dict(os.environ,
        ASAN_OPTIONS='detect_leaks=0'), capture_output=True, text=True)
    if checked.returncode:
        print(checked.stdout + checked.stderr, flush=True)
    checked.check_returncode()
    (output / 'host-check.txt').write_text(checked.stdout)
    return dict(status='pass', output=checked.stdout.strip(),
                source_sha256={name: sha(path) for name, path in sources.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cpu', choices=['486', 'pentium-mmx'])
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--control', type=Path)
    parser.add_argument('--skip-benchmark', action='store_true')
    parser.add_argument('--calibrate', action='store_true')
    parser.add_argument('--cases', nargs='+')
    args = parser.parse_args()
    root = images.ROOT
    package = root / '_output' / f'libretto-{args.cpu}-fat32'
    output = package / ('clock-calibration' if args.calibrate else 'clock')
    output.mkdir(parents=True, exist_ok=True)
    host = host_check(output)
    tools = output / 'tools'
    tools.mkdir(exist_ok=True)
    env = dict(os.environ, WATCOM=str(root / '_watcom'), LIBRETTO_CPU=args.cpu,
               LIBRETTO_RAM_MB='20', LIBRETTO_TUNE='4' if args.cpu == '486' else '5')
    env['PATH'] = str(root / '_watcom/binl64') + os.pathsep + env['PATH']
    if args.control:
        shutil.copy2(args.control, output / 'control.sys')
    else:
        compare.BASELINE = BASELINE
        compare.build_control(args.cpu, output, env)
    candidate = args.kernel or package / 'KERNEL.SYS'
    shutil.copy2(output / 'control.sys' if args.calibrate else candidate,
                 output / 'candidate.sys')
    images.run(['nasm', '-f', 'obj', root / 'scripts/libretto/dos/clockhook.asm',
                '-o', tools / 'hook.obj'])
    images.run(['wcl', '-zq', '-bt=dos', '-ms', '-0', '-os', '-wx', '-we', '-k4096',
                '-I' + str(root / '_watcom/h'), '-fe=CLKTEST.EXE',
                root / 'scripts/libretto/dos/clocktest.c', tools / 'hook.obj'], cwd=tools, env=env)
    for name, target in [('mbr', 'mbr.bin'), ('poweroff', 'POWEROFF.COM'),
                         ('memstat', 'MEMSTAT.COM'), ('clockdev', 'CLOCKDEV.SYS')]:
        images.run(['nasm', '-f', 'bin', root / f'scripts/libretto/dos/{name}.asm',
                    '-o', tools / target])
    payload = tools / 'payload'
    payload.mkdir(exist_ok=True)
    for name in ['COMMAND.COM', 'HIMEMX.EXE', 'JEMMEX.EXE']:
        shutil.copy2(root / '_downloads/runtime-extracted' / name, payload / name)
    for name in ['CLKTEST.EXE', 'POWEROFF.COM', 'MEMSTAT.COM', 'CLOCKDEV.SYS']:
        shutil.copy2(tools / name, payload / name)
    results, raw = [], []
    report = dict(baseline_commit=BASELINE, candidate_commit=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True).strip(),
        working_tree_dirty=bool(subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=no'], text=True).strip()),
        control_override=bool(args.control), calibration=args.calibrate, host=host,
        cpu=args.cpu, exact_buffers=20, source='INT 1Ah test hook',
        kernel_sha256={v: sha(output / (v + '.sys')) for v in ['control', 'candidate']},
        kernel_bytes={v: (output / (v + '.sys')).stat().st_size for v in ['control', 'candidate']},
        boots=results, samples=raw,
        limitations=['QEMU instruction counts are not native cycles or FPS.',
                     'A deterministic BIOS hook isolates kernel conversion work; normal BIOS boots run separately.'])
    counter = tools / 'counter.so'
    if not args.skip_benchmark:
        version = subprocess.check_output(['qemu-system-i386', '--version'], text=True).splitlines()[0]
        assert 'version 8.2.' in version, 'Counter header requires QEMU 8.2'
        report['qemu_version'] = version
        images.run(['gcc', '-shared', '-fPIC', '-fvisibility=hidden', '-O2', '-Wall',
                    '-Wextra', '-Werror', root / 'scripts/libretto/qemu/instruction_count.c',
                    '-o', counter])

    def boot(variant, profile, ram, mode, label, bench=False):
        config = images.config(profile).replace('BUFFERS=20\n', 'BUFFERS=-20\n')
        if mode == 'external':
            config += 'DEVICE=C:\\CLOCKDEV.SYS\n'
        images.dos_text(payload / 'FDCONFIG.SYS', config)
        images.dos_text(payload / 'AUTOEXEC.BAT',
            '@ECHO OFF\nMEMSTAT > MEMORY.TXT\nCLKTEST ' + mode + ' > CLOCKLOG.TXT\n'
            'IF ERRORLEVEL 1 GOTO FAIL\nECHO PASS > RESULT.TXT\nPOWEROFF\nGOTO END\n'
            ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n:END\n')
        shutil.copy2(output / (variant + '.sys'), payload / 'KERNEL.SYS')
        disk = tools / (label + '.img')
        images.make_disk(payload, disk, tools / 'mbr.bin')
        command = [root / 'scripts/libretto/qemu-target.sh']
        counts = output / (label + '-instructions.csv')
        if bench:
            command += ['-accel', 'tcg,thread=single', '-smp', '1,maxcpus=1',
                        '-icount', 'shift=3,align=off,sleep=off', '-rtc',
                        'base=2026-01-01T00:00:00,clock=vm', '-plugin',
                        f'file={counter},out={counts}']
        command += ['-drive', f'file={disk},format=raw,if=ide', '-boot', 'c',
                    '-display', 'none', '-no-reboot']
        try:
            with (output / (label + '.qemu.log')).open('wb') as log:
                images.run(command, env=dict(env, LIBRETTO_RAM_MB=str(ram)),
                           timeout=180, stdout=log, stderr=subprocess.STDOUT)
            text = images.mread(disk, 'CLOCKLOG.TXT').decode('ascii')
            (output / (label + '.txt')).write_text(text)
            assert images.mread(disk, 'RESULT.TXT').strip() == b'PASS', text
            lines = text.splitlines()
            match = re.fullmatch(r'CLOCK_CONFIG buffers=(\d+) bufloc=(\d+)', lines[0])
            assert match and int(match[1]) == 20, lines[:2]
            assert int(match[2]) == int(profile != 'basic'), lines[0]
            memory = dict((k, int(v)) for k, v in (line.split('=', 1) for line in
                images.mread(disk, 'MEMORY.TXT').decode('ascii').splitlines()))
            result = dict(label=label, variant=variant, profile=profile, ram_mib=ram,
                          mode=mode, status='pass', nbuffers=int(match[1]),
                          bufloc=int(match[2]), memory=memory)
            if bench:
                rows = list(csv.DictReader(io.StringIO('\n'.join(lines[1:]))))
                with counts.open() as f:
                    measured = list(csv.DictReader(f))
                assert len(rows) == len(measured) == 30
                for i, (row, sample) in enumerate(zip(rows, measured)):
                    assert row['scenario'] == SCENARIOS[i % 6]
                    assert int(sample['marker_errors']) == 0 and int(sample['interval']) == i + 1
                    assert int(row['bios_reads']) == int(row['calls']) == 256
                    raw.append(dict(variant=variant, boot=label, trial=int(row['trial']),
                        scenario=row['scenario'], calls=256,
                        guest_instructions=int(sample['guest_instructions']),
                        non_rom_instructions=int(sample['non_rom_instructions'])))
            else:
                assert 'PASS:' in text, text
                result['guest'] = '\n'.join(lines[1:])
            results.append(result)
            print('CLOCK_PASS ' + label, flush=True)
        except Exception:
            for name in ['CLOCKLOG.TXT', 'RESULT.TXT']:
                try:
                    print(name + ': ' + images.mread(disk, name).decode('ascii', errors='replace'))
                except subprocess.CalledProcessError:
                    pass
            raise
        finally:
            (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
        disk.unlink()

    if not args.calibrate:
        for variant in ['control', 'candidate']:
            for profile in ['basic', 'xms', 'ems']:
                for ram in [20, 32]:
                    label = f'{variant}-{profile}-{ram}'
                    if not args.cases or label in args.cases:
                        boot(variant, profile, ram, 'all' if profile == 'xms' and ram == 20 else 'check', label)
            label = variant + '-external'
            if not args.cases or label in args.cases:
                boot(variant, 'xms', 20, 'external', label)
    if not args.skip_benchmark:
        for i, variant in enumerate(['control', 'candidate', 'candidate', 'control']):
            boot(variant, 'xms', 20, 'bench', f'bench-{i}-{variant}', True)
        summaries = []
        for scenario in SCENARIOS:
            samples = {v: [r['non_rom_instructions'] for r in raw if r['variant'] == v and
                r['scenario'] == scenario] for v in ['control', 'candidate']}
            assert all(len(s) == 10 for s in samples.values())
            a, b = samples['control'], samples['candidate']
            summaries.append(dict(scenario=scenario, samples_per_variant=10,
                control_median=statistics.median(a), candidate_median=statistics.median(b),
                control_range=[min(a), max(a)], candidate_range=[min(b), max(b)],
                paired_change_percent_median=statistics.median([(y / x - 1) * 100 for x, y in zip(a, b)])))
        report['summaries'] = summaries
        if args.calibrate:
            assert report['kernel_sha256']['control'] == report['kernel_sha256']['candidate']
            report['max_calibration_change_percent'] = max(abs(r['paired_change_percent_median']) for r in summaries)
            assert report['max_calibration_change_percent'] <= 0.1, summaries
    (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Exercise real MZ relocation loading, error prefixes, stack use and service costs."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import compare
import chains
import images

BASELINE = '1c43e901dc699dce0a0a89301fccb09eddb6096d'
SCENARIOS = ['B0.EXE', 'B8.EXE', 'B128.EXE', 'B4096.EXE']


def fixture(path, count, size=8192, table=28, available=None, tail=0):
    """A conventional MZ, or an intact body followed by a deliberately short table."""
    short = available is not None
    available = count if available is None else available
    header = 2 if short else (table + count * 4 + 15) // 16
    length = header * 16 + size
    body = bytearray((i * 37 + (i >> 8)) & 255 for i in range(size))
    body[:5] = bytes.fromhex('b8074ccd21')  # EXIT 7, safe from relocation targets
    data = bytearray(max(length, table + available * 4 + tail))
    # EXE loader rounds its image to pages; choose a page-aligned header+body
    # for short tables too. Body comparisons cover the requested image bytes.
    fields = [0x5a4d, length % 512, (length + 511) // 512, count, header,
              64, 64, size // 16, 1024, 0, 0, 0, table, 0]
    struct.pack_into('<14H', data, 0, *fields)
    data[header * 16:header * 16 + size] = body
    targets = [(0x200, 0), (0x201, 0), (0x200, 0), (0x1f0, 1),
               (0xfffe, 0) if size > 65536 else (0x400, 1),
               (0, 0x1000) if size > 65536 else (0x600, 3)]
    for i in range(available):
        off, seg = targets[i % len(targets)]
        struct.pack_into('<HH', data, table + 4 * i, off, seg)
    if short:
        data = data[:table + available * 4 + tail]
    path.write_bytes(data)
    return header


def fixtures(payload):
    records = []
    counts = [0, 1, 7, 8, 9, 15, 16, 17, 127, 128, 129,
              16383, 16384, 16385, 32767, 32768, 65535]
    for i, count in enumerate(counts):
        name = f'F{i:03}.EXE'
        size = 69632 if count == 129 else 8192
        table = 511 if count == 17 else 28
        header = fixture(payload / name, count, size, table)
        records.append((name, count, count, header, table, 0,
                        int(count in [0, 1, 8, 9, 129]), size))
    for available in range(10):
        for tail in range(4):
            name = f'S{available}{tail}.EXE'
            header = fixture(payload / name, 17, size=8160, table=0x3000,
                             available=available, tail=tail)
            records.append((name, 17, available, header, 0x3000, 13,
                            int(available == 9 and tail == 3), 8160))
    (payload / 'CASES.DAT').write_bytes(b''.join(struct.pack(
        '<12s6HI', name.encode(), *rest) for name, *rest in records))
    for count, name in zip([0, 8, 128, 4096], SCENARIOS):
        fixture(payload / name, count)
    fixture(payload / 'RUN.EXE', 17)
    fixture(payload / 'AIO.EXE', 256, size=8160, table=0x3001, available=256)
    (payload / 'RUN.COM').write_bytes(bytes.fromhex('b8074ccd21'))
    return len(records)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host_check(output):
    source = (images.ROOT / 'kernel/task.c').read_text()
    block = re.search(r'  \{ +/\* relocate the image.*?\n  \}\n', source, re.S).group()
    (output / 'exec-under-test.h').write_text(block)
    binary = output / 'host-check'
    images.run(['gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-strict-aliasing', '-fsanitize=address', '-I' + str(output),
                images.ROOT / 'scripts/libretto/exec_host.c', '-o', binary])
    checked = subprocess.run([str(binary)], env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'),
                             capture_output=True, text=True)
    if checked.returncode:
        print(checked.stdout + checked.stderr, flush=True)
    checked.check_returncode()
    (output / 'host-check.txt').write_text(checked.stdout)
    return dict(status='pass', output=checked.stdout.strip(),
                source_sha256=sha(images.ROOT / 'kernel/task.c'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('cpu', choices=['486', 'pentium-mmx'])
    p.add_argument('--kernel', type=Path)
    p.add_argument('--control', type=Path)
    p.add_argument('--skip-benchmark', action='store_true')
    p.add_argument('--calibrate', action='store_true')
    p.add_argument('--cases', nargs='+')
    args = p.parse_args()
    root = images.ROOT
    package = root / '_output' / f'libretto-{args.cpu}-fat32'
    output = package / ('exec-calibration' if args.calibrate else 'exec')
    tools = output / 'tools'
    tools.mkdir(parents=True, exist_ok=True)
    host = host_check(output)
    env = dict(os.environ, WATCOM=str(root / '_watcom'), LIBRETTO_CPU=args.cpu,
               LIBRETTO_TUNE='4' if args.cpu == '486' else '5')
    env['PATH'] = str(root / '_watcom/binl64') + os.pathsep + env['PATH']
    if args.control:
        shutil.copy2(args.control, output / 'control.sys')
    else:
        compare.BASELINE = BASELINE
        compare.build_control(args.cpu, output, env)
    candidate = args.kernel or package / 'KERNEL.SYS'
    shutil.copy2(output / 'control.sys' if args.calibrate else candidate, output / 'candidate.sys')
    images.run(['wcl', '-zq', '-bt=dos', '-ms', '-0', '-os', '-wx', '-we', '-k4096',
                '-I' + str(root / '_watcom/h'), '-fe=EXECTEST.EXE',
                root / 'scripts/libretto/dos/exectest.c'], cwd=tools, env=env)
    for name, target in [('mbr', 'mbr.bin'), ('poweroff', 'POWEROFF.COM'),
                         ('memstat', 'MEMSTAT.COM')]:
        images.run(['nasm', '-f', 'bin', root / f'scripts/libretto/dos/{name}.asm', '-o', tools / target])
    payload = tools / 'payload'
    payload.mkdir(exist_ok=True)
    for name in ['COMMAND.COM', 'HIMEMX.EXE', 'JEMMEX.EXE']:
        shutil.copy2(root / '_downloads/runtime-extracted' / name, payload / name)
    for name in ['EXECTEST.EXE', 'POWEROFF.COM', 'MEMSTAT.COM']:
        shutil.copy2(tools / name, payload / name)
    nfixtures = fixtures(payload)
    results, raw = [], []
    report = dict(baseline_commit=BASELINE, candidate_commit=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True).strip(),
        working_tree_dirty=bool(subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=no'], text=True).strip()),
        control_override=bool(args.control), calibration=args.calibrate, cpu=args.cpu,
        fixtures=nfixtures, host=host, exact_buffers=20, boots=results, samples=raw,
        kernel_sha256={v: sha(output / (v + '.sys')) for v in ['control', 'candidate']},
        kernel_bytes={v: (output / (v + '.sys')).stat().st_size for v in ['control', 'candidate']},
        limitations=['Guest instruction counts are not native cycles or FPS.',
                     'Overlay benchmarks include open/seek/body read/close; only relocations change.',
                     'Network redirectors are covered by a host request-trace test, not a network DOS boot.'])
    counter = tools / 'counter.so'
    if not args.skip_benchmark:
        version = subprocess.check_output(['qemu-system-i386', '--version'], text=True).splitlines()[0]
        assert 'version 8.2.' in version, 'Counter header requires QEMU 8.2'
        report['qemu_version'] = version
        images.run(['gcc', '-shared', '-fPIC', '-fvisibility=hidden', '-O2', '-Wall',
                    '-Wextra', '-Werror', root / 'scripts/libretto/qemu/instruction_count.c', '-o', counter])

    def boot(variant, profile, ram, mode, label, bench=False):
        config = images.config(profile)
        if mode != 'probe':
            config = config.replace('BUFFERS=20\n', 'BUFFERS=-20\n')
        images.dos_text(payload / 'FDCONFIG.SYS', config)
        images.dos_text(payload / 'AUTOEXEC.BAT',
            '@ECHO OFF\nMEMSTAT > MEMORY.TXT\nEXECTEST ' + mode + ' > EXECLOG.TXT\n'
            'IF ERRORLEVEL 1 GOTO FAIL\nECHO PASS > RESULT.TXT\nPOWEROFF\nGOTO END\n'
            ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n:END\n')
        shutil.copy2(output / (variant + '.sys'), payload / 'KERNEL.SYS')
        disk = tools / (label + '.img')
        images.make_disk(payload, disk, tools / 'mbr.bin')
        drive = str(disk)
        if mode == 'io':
            g, blocks = chains.chain(disk, b'AIO     EXE')
            assert g['bps'] == 512 and g['spc'] == 1
            # Fail the sector after 511 table bytes: 127 full entries and a partial one.
            sector = (g['data'] + (blocks[0x3200 // 512] - 2) * 512) // 512
            fault = tools / (label + '.conf')
            fault.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                             f'sector = "{sector}"\nonce = "off"\n')
            drive = f'blkdebug:{fault}:{disk}'
        command = [root / 'scripts/libretto/qemu-target.sh']
        counts = output / (label + '-instructions.csv')
        if bench:
            command += ['-accel', 'tcg,thread=single', '-smp', '1,maxcpus=1',
                        '-icount', 'shift=3,align=off,sleep=off', '-rtc',
                        'base=2026-01-01T00:00:00,clock=vm', '-plugin', f'file={counter},out={counts}']
        command += ['-drive', f'file={drive},format=raw,if=ide', '-boot', 'c', '-display', 'none', '-no-reboot']
        try:
            with (output / (label + '.qemu.log')).open('wb') as log:
                images.run(command, env=dict(env, LIBRETTO_RAM_MB=str(ram)), timeout=180,
                           stdout=log, stderr=subprocess.STDOUT)
            guest = images.mread(disk, 'EXECLOG.TXT').decode('ascii')
            (output / (label + '.txt')).write_text(guest)
            assert images.mread(disk, 'RESULT.TXT').strip() == b'PASS', guest
            lines = guest.splitlines()
            fields = dict(field.split('=') for field in lines[0].split()[1:])
            buffers, location = int(fields['buffers']), int(fields['bufloc'])
            assert (buffers >= 20 if mode == 'probe' else buffers == 20), lines[0]
            assert location == int(profile != 'basic'), lines[0]
            memory = dict((k, int(v)) for k, v in (line.split('=', 1) for line in
                images.mread(disk, 'MEMORY.TXT').decode('ascii').splitlines()))
            results.append(dict(label=label, variant=variant, profile=profile, ram_mib=ram,
                mode=mode, status='pass', nbuffers=buffers, bufloc=location, memory=memory,
                guest='\n'.join(lines[1:])))
            if mode == 'io':
                chains.edges.fsck(disk, tools)
            if bench:
                rows = list(csv.DictReader(io.StringIO('\n'.join(lines[1:]))))
                with counts.open() as f:
                    measured = list(csv.DictReader(f))
                assert len(rows) == len(measured) == 20
                for i, (row, sample) in enumerate(zip(rows, measured)):
                    assert row['scenario'] == SCENARIOS[i % 4]
                    assert int(sample['marker_errors']) == 0 and int(sample['interval']) == i + 1
                    raw.append(dict(variant=variant, boot=label, trial=int(row['trial']),
                        scenario=row['scenario'], calls=16,
                        guest_instructions=int(sample['guest_instructions']),
                        non_rom_instructions=int(sample['non_rom_instructions'])))
            print('EXEC_PASS ' + label, flush=True)
        except Exception:
            for name in ['EXECLOG.TXT', 'RESULT.TXT']:
                try:
                    print(name + ': ' + images.mread(disk, name).decode('ascii', errors='replace'), flush=True)
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
            label = variant + '-automatic-buffers'
            if not args.cases or label in args.cases:
                boot(variant, 'xms', 20, 'probe', label)
            label = variant + '-io'
            if not args.cases or label in args.cases:
                boot(variant, 'xms', 20, 'io', label)
        auto = [r['nbuffers'] for r in results if r['mode'] == 'probe']
        if len(auto) == 2:
            assert auto[0] == auto[1], 'Automatic HMA buffer capacity changed'
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

#!/usr/bin/env python3
"""Boot regressions for JFT ownership/lifetime and CONFIG.SYS INSTALL limits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cpu', choices=['486', 'pentium-mmx'])
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--label', default='candidate')
    parser.add_argument('--cases', nargs='+')
    args = parser.parse_args()
    root = images.ROOT
    package = root / '_output' / f'libretto-{args.cpu}-fat32'
    kernel = (args.kernel or package / 'KERNEL.SYS').resolve()
    output = package / ('kernel-checks-' + args.label)
    output.mkdir(parents=True, exist_ok=True)
    tools = output / 'tools'
    tools.mkdir(exist_ok=True)
    watcom = Path(os.environ.get('WATCOM', str(root / '_watcom')))
    env = dict(os.environ, WATCOM=str(watcom), LIBRETTO_CPU=args.cpu)
    env['PATH'] = str(watcom / 'binl64') + os.pathsep + env['PATH']
    images.run(['wcl', '-zq', '-bt=dos', '-ms', '-0', '-os', '-wx', '-we',
                '-k4096', '-I' + str(watcom / 'h'), '-fe=JFTCHECK.EXE',
                root / 'scripts/libretto/dos/jftcheck.c'], cwd=tools, env=env)
    for name, target in [('mbr', 'mbr.bin'), ('poweroff', 'POWEROFF.COM'),
                         ('installmark', 'MARK.COM')]:
        images.run(['nasm', '-f', 'bin', root / f'scripts/libretto/dos/{name}.asm',
                    '-o', tools / target])
    payload = tools / 'payload'
    payload.mkdir(exist_ok=True)
    runtime = root / '_downloads/runtime-extracted'
    for name in ['COMMAND.COM', 'HIMEMX.EXE', 'JEMMEX.EXE']:
        shutil.copy2(runtime / name, payload / name)
    for name in ['JFTCHECK.EXE', 'POWEROFF.COM', 'MARK.COM']:
        shutil.copy2(tools / name, payload / name)
    shutil.copy2(kernel, payload / 'KERNEL.SYS')
    results = []
    cases = []
    for profile in ['basic', 'xms', 'ems']:
        for ram in [20, 32]:
            cases.append((f'jft-{profile}-{ram}', profile, ram, None))
    for n in [9, 10, 11]:
        cases.append((f'install-{n}', 'xms', 20, n))
    for name, profile, ram, installs in cases:
        if args.cases and name not in args.cases:
            continue
        config = images.config(profile)
        if installs is not None:
            config += ''.join(('INSTALLHIGH' if i % 2 else 'INSTALL') +
                              '=C:\\MARK.COM\n' for i in range(installs))
        images.dos_text(payload / 'FDCONFIG.SYS', config)
        batch = '@ECHO OFF\n'
        if installs is None:
            for i, mode in enumerate(['growth', '0', '1', '2']):
                batch += (f'JFTCHECK {mode} ' + ('>' if i == 0 else '>>') +
                          ' CHECKLOG.TXT\nIF ERRORLEVEL 1 GOTO FAIL\n')
        else:
            batch += 'ECHO INSTALL_BOOT_OK > CHECKLOG.TXT\n'
        batch += ('ECHO PASS > RESULT.TXT\nPOWEROFF\nGOTO END\n'
                  ':FAIL\nECHO FAIL > RESULT.TXT\nPOWEROFF\n:END\n')
        images.dos_text(payload / 'AUTOEXEC.BAT', batch)
        disk = tools / (name + '.img')
        images.make_disk(payload, disk, tools / 'mbr.bin')
        debug = output / (name + '.debug')
        debug.unlink(missing_ok=True)
        command = [root / 'scripts/libretto/qemu-target.sh', '-drive',
                   f'file={disk},format=raw,if=ide', '-boot', 'c', '-display',
                   'none', '-no-reboot', '-debugcon', f'file:{debug}']
        try:
            with (output / (name + '.qemu.log')).open('wb') as log:
                images.run(command, env=dict(env, LIBRETTO_RAM_MB=str(ram)),
                           timeout=120, stdout=log, stderr=subprocess.STDOUT)
            guest = images.mread(disk, 'CHECKLOG.TXT').decode('ascii')
            (output / (name + '.txt')).write_text(guest)
            assert images.mread(disk, 'RESULT.TXT').strip() == b'PASS', guest
            if installs is not None:
                assert debug.read_bytes() == b'I' * min(installs, 10), (
                    'INSTALL execution count', debug.read_bytes())
            else:
                assert guest.count('PASS:') == 4, guest
            results.append(dict(case=name, status='pass', guest=guest.strip()))
            print('KERNEL_CHECK_PASS ' + name, flush=True)
        except Exception:
            for filename in ['CHECKLOG.TXT', 'RESULT.TXT']:
                try:
                    print(filename + ': ' + images.mread(disk, filename).decode(
                        'ascii', errors='replace'), flush=True)
                except subprocess.CalledProcessError:
                    pass
            raise
        finally:
            (output / 'results.json').write_text(json.dumps(dict(
                kernel_sha256=hashlib.sha256(kernel.read_bytes()).hexdigest(),
                results=results), indent=2) + '\n')
        disk.unlink()
    assert results, 'No matching cases'


if __name__ == '__main__':
    main()

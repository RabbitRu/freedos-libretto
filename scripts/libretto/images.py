#!/usr/bin/env python3
"""Build standalone FAT32 disks and validate DOS results on fresh image copies."""
import gzip
import csv
import io
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import socket
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OFFSET = 2048 * 512
SECTORS = 131072


def run(args, **kw):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kw)


def dos_text(path, text):
    path.write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii'))


def config(profile, interactive=False):
    header = ('MENU FreeDOS Libretto: 0 Basic, 1 XMS/HMA, 2 XMS/EMS/UMB\n'
              'MENUDEFAULT=0,5\n') if interactive else ''
    if interactive:
        drivers = ('0?ECHO Basic profile\n1?DEVICE=C:\\HIMEMX.EXE\n1?DOS=HIGH\n'
                   '2?DEVICE=C:\\JEMMEX.EXE\n2?DOS=HIGH,UMB\n2?DOSDATA=UMB\n')
    elif profile == 'xms':
        drivers = 'DEVICE=C:\\HIMEMX.EXE\nDOS=HIGH\n'
    elif profile == 'ems':
        drivers = 'DEVICE=C:\\JEMMEX.EXE\nDOS=HIGH,UMB\nDOSDATA=UMB\n'
    else:
        drivers = 'DOS=LOW,NOUMB\n'
    return header + drivers + ('FILES=20\nBUFFERS=20\nLASTDRIVE=E\nSTACKS=9,256\n'
                               'SHELL=C:\\COMMAND.COM C:\\ /E:512 /P\n')

AUTOEXEC = r'''@ECHO OFF
PATH=C:\
PROMPT $P$G
MEMSTAT > MEMORY.TXT
IF EXIST AUTOTEST.RUN GOTO TEST
ECHO FreeDOS Libretto - interactive FAT32 disk
TYPE MEMORY.TXT
ECHO Commands: MEMSTAT, FSVERIFY, DOSBENCH 10, DIR, TYPE, COPY
ECHO FSVERIFY creates its own FSWORK directory and needs a fresh disk.
GOTO END
:TEST
FSVERIFY > FSLOG.TXT
IF ERRORLEVEL 1 GOTO FAILED
DOSBENCH 1 > BENCH.CSV
IF ERRORLEVEL 1 GOTO FAILED
ECHO PASS > RESULT.TXT
POWEROFF
GOTO END
:FAILED
ECHO FAIL > RESULT.TXT
POWEROFF
:END
'''


def make_disk(payload, image, mbr):
    entries = [str(p) for p in sorted(payload.iterdir()) if p.is_file()]
    # Boot image writer from upstream includes the tested FreeDOS FAT32 LBA VBR.
    run(['nasm', ROOT/'test/bootimg/bootimg.asm', '-I'+str(ROOT/'test/lmacros')+'/',
         '-D_MBR=1', '-D_MBR_GAP_SIZE_SECTORS=2048', '-D_BPE=32', '-D_SPC=1',
         '-D_SPI='+str(SECTORS), '-D_SPF=1024', '-D_NUMRESERVED=32',
         '-D_CHS_HEADS=16', '-D_CHS_SECTORS=63', '-D_UNIT=80h',
         '-D_WARN_DEFAULT_OFF=1', '-D_WARN_TOOMANYFAT=0', '-D_WARN_ALIGNDATA=0',
         '-D_BOOTPATCHFILE='+repr(str(ROOT/'boot/fat32lba.bin')),
         '-D_MBRPATCHFILE='+repr(str(mbr)), '-D_PAYLOADFILE='+','.join(repr(p) for p in entries),
         '-o', image])


def mread(image, name):
    return subprocess.check_output(['mtype', '-i', str(image)+'@@'+str(OFFSET), '::'+name])


def fragments(image):
    """Independent FAT32 chain walk verifies actual fragmentation, not its intent."""
    with image.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as d:
        bps = struct.unpack_from('<H', d, OFFSET+11)[0]
        spc = d[OFFSET+13]
        reserved = struct.unpack_from('<H', d, OFFSET+14)[0]
        fats = d[OFFSET+16]
        spf = struct.unpack_from('<I', d, OFFSET+36)[0]
        root = struct.unpack_from('<I', d, OFFSET+44)[0]
        total = struct.unpack_from('<I', d, OFFSET+32)[0]
        cluster_count = (total-reserved-fats*spf)//spc
        assert bps == 512 and cluster_count >= 65525, 'not a valid FAT32 volume'
        fat = OFFSET+reserved*bps
        data = fat+fats*spf*bps
        def chain(first):
            seen = set()
            while first < 0x0ffffff8:
                assert 2 <= first < cluster_count+2 and first not in seen, 'invalid FAT chain'
                seen.add(first)
                yield first
                first = struct.unpack_from('<I', d, fat+first*4)[0] & 0x0fffffff
        def find(first, short_name):
            for c in chain(first):
                start = data+(c-2)*bps*spc
                for off in range(start, start+bps*spc, 32):
                    if d[off] == 0: raise AssertionError('missing '+str(short_name))
                    if d[off:off+11] == short_name:
                        return struct.unpack_from('<H',d,off+26)[0] | (struct.unpack_from('<H',d,off+20)[0]<<16)
            raise AssertionError('missing directory entry')
        folder = find(root,b'FSWORK     ')
        result = {}
        for filename in ['FRAGA','FRAGB']:
            c = list(chain(find(folder, (filename.ljust(8)+'BIN').encode())))
            result[filename] = 1 + sum(b != a+1 for a,b in zip(c,c[1:]))
            assert result[filename] > 1, 'fragmentation test did not produce fragmented data'
        return result


def validate(image, profile, scratch):
    assert mread(image,'RESULT.TXT').strip() == b'PASS', mread(image,'FSLOG.TXT')
    values = {}
    for line in mread(image,'MEMORY.TXT').decode('ascii').splitlines():
        k,v = line.split('=',1)
        values[k] = int(v)
    assert 0 < values['largest_conventional_block_bytes_while_probe_loaded'] <= values['conventional_free_bytes_while_probe_loaded'] <= 640*1024
    assert values['xms_present'] == int(profile != 'basic'), values
    assert values['ems_present'] == int(profile == 'ems'), values
    assert values['dos_in_hma'] == int(profile != 'basic'), values
    if profile == 'ems': assert values['umb_enumeration_supported'] == 1, values
    for name, seed in [('FRAGA',0x5a), ('FRAGB',0xa5)]:
        actual = mread(image,'FSWORK/'+name+'.BIN')
        expected = bytes(((i*17+(i>>8))^seed)&255 for i in range(131072))
        assert actual == expected, 'independent host data verification failed'
    bench_text = mread(image,'BENCH.CSV').decode('ascii')
    bench = list(csv.DictReader(io.StringIO(bench_text)))
    assert {r['scenario'] for r in bench} == {'write_1m_flush','repeated_read_16m','random_read_1m','small_files_100'}
    assert len(bench) == 4
    for row in bench:
        assert int(row['run']) == 1 and int(row['bios_ticks']) >= 0
    (scratch/'bench.csv').write_text(bench_text)
    counts = fragments(image)
    # fsck.fat receives a filesystem image, not an MBR disk.
    volume = scratch/'volume.img'
    with image.open('rb') as src, volume.open('wb') as dst:
        src.seek(OFFSET)
        shutil.copyfileobj(src,dst)
    checked = subprocess.run(['fsck.fat','-n',str(volume)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (scratch/'fsck.txt').write_text(checked.stdout)
    print(checked.stdout, flush=True)
    assert checked.returncode == 0, 'independent fsck.fat check failed'
    return dict(profile=profile, memory=values, fragments=counts,
                filesystem_test=mread(image,'FSLOG.TXT').decode('ascii').strip(), fsck='pass', benchmark=bench, benchmark_environment='QEMU')


def interactive_smoke(image, cpu, tools):
    """Check the real menu image reaches a prompt and accepts a command."""
    scratch = tools/'interactive-smoke'
    scratch.mkdir(exist_ok=True)
    disk = scratch/'disk.img'
    shutil.copy2(image,disk)
    batch = scratch/'SMOKE.BAT'
    dos_text(batch,'@ECHO OFF\nECHO PROMPT_OK > READY.TXT\nPOWEROFF\n')
    run(['mcopy','-i',str(disk)+'@@'+str(OFFSET),batch,'::SMOKE.BAT'])
    with tempfile.TemporaryDirectory(prefix='lb-smoke-') as tmp:
        monitor = Path(tmp)/'monitor'
        command = [str(ROOT/'scripts/libretto/qemu-target.sh'),'-drive',f'file={disk},format=raw,if=ide',
                   '-boot','c','-display','none','-no-reboot','-monitor',f'unix:{monitor},server=on,wait=off']
        env = dict(os.environ,LIBRETTO_CPU=cpu,LIBRETTO_RAM_MB='20')
        with (scratch/'qemu.txt').open('wb') as log:
            process = subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic()+40
                while time.monotonic()<deadline:
                    probe = subprocess.run(['mtype','-i',str(disk)+'@@'+str(OFFSET),'::MEMORY.TXT'],capture_output=True)
                    if probe.returncode==0 and b'ems_total_16k_pages=' in probe.stdout:
                        break
                    assert process.poll() is None, 'interactive QEMU exited before startup'
                    time.sleep(0.25)
                else:
                    raise AssertionError('interactive shell startup timed out')
                time.sleep(0.5)
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.settimeout(3)
                    connection.connect(str(monitor))
                    connection.recv(4096)
                    for key in ['s','m','o','k','e','ret']:
                        connection.sendall(('sendkey '+key+' 30\n').encode())
                        time.sleep(0.10)
                        connection.recv(4096)
                assert process.wait(timeout=30)==0, 'interactive prompt command failed'
                assert mread(disk,'READY.TXT').strip()==b'PROMPT_OK'
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    disk.unlink()
    return 'pass'


def main():
    output = Path(sys.argv[1]).resolve()
    cpu = sys.argv[2]
    tools = output/'tools'
    tools.mkdir(exist_ok=True)
    runtime = ROOT/'_downloads/runtime-extracted'
    for name in ['mbr','memstat','poweroff']:
        run(['nasm','-f','bin',ROOT/f'scripts/libretto/dos/{name}.asm','-o',tools/(name+'.bin' if name=='mbr' else name.upper()+'.COM')])
    for utility in ['fsverify','dosbench']:
        run(['wcl','-zq','-bt=dos','-ms','-0','-os','-k4096','-I'+str(Path(os.environ['WATCOM'])/'h'),'-fe='+utility.upper()+'.EXE', ROOT/f'scripts/libretto/dos/{utility}.c'], cwd=tools)
    run(['python3', ROOT/'scripts/libretto/runtime.py', runtime])
    payload = tools/'payload'
    payload.mkdir(exist_ok=True)
    for name in ['COMMAND.COM','HIMEMX.EXE','JEMMEX.EXE']:
        shutil.copy2(runtime/name,payload/name)
    for name in ['MEMSTAT.COM','FSVERIFY.EXE','DOSBENCH.EXE','POWEROFF.COM']:
        shutil.copy2(tools/name,payload/name)
    shutil.copy2(output/'KERNEL.SYS',payload/'KERNEL.SYS')
    dos_text(payload/'AUTOEXEC.BAT',AUTOEXEC)
    dos_text(payload/'README.TXT','FreeDOS Libretto. See the repository LIBRETTO.md for usage and measurement limits.\n')
    dos_text(payload/'BUILD.TXT',f'CPU={cpu}\nKERNEL_SHA256={hashlib.sha256((output/"KERNEL.SYS").read_bytes()).hexdigest()}\n')
    dos_text(payload/'FDCONFIG.SYS',config('basic',interactive=True))
    interactive = output/'interactive-fat32.img'
    make_disk(payload,interactive,tools/'mbr.bin')
    results = []
    for profile in ['basic','xms','ems']:
        dos_text(payload/'FDCONFIG.SYS',config(profile))
        (payload/'AUTOTEST.RUN').write_bytes(b'CI test mode\r\n')
        image = tools/(profile+'.img')
        make_disk(payload,image,tools/'mbr.bin')
        for ram in [20,32]:
            scratch = tools/f'{profile}-{ram}'
            scratch.mkdir(exist_ok=True)
            disk = scratch/'disk.img'
            shutil.copy2(image,disk)
            command = [str(ROOT/'scripts/libretto/qemu-target.sh'),'-drive',f'file={disk},format=raw,if=ide', '-boot','c','-display','none','-no-reboot']
            env = dict(os.environ,LIBRETTO_CPU=cpu,LIBRETTO_RAM_MB=str(ram))
            try:
                with (scratch/'qemu.txt').open('wb') as log:
                    run(command,env=env,timeout=120,stdout=log,stderr=subprocess.STDOUT)
                result = validate(disk,profile,scratch)
                result['ram_mib'] = ram
                results.append(result)
                (output/'fat32-tests.json').write_text(json.dumps(results,indent=2)+'\n')
                shutil.copy2(scratch/'bench.csv',output/f'bench-{profile}-{ram}.csv')
                print('FAT32_RESULT '+json.dumps(result),flush=True)
            except Exception:
                for name in ['MEMORY.TXT','FSLOG.TXT','BENCH.CSV','RESULT.TXT']:
                    try: print(name+': '+mread(disk,name).decode('ascii',errors='replace'),flush=True)
                    except subprocess.CalledProcessError: pass
                raise
            disk.unlink()
            (scratch/'volume.img').unlink()
        image.unlink()
    shutil.copy2(runtime/'RUNTIME.JSON',output/'runtime.json')
    shutil.copytree(runtime/'LICENSES',output/'LICENSES',dirs_exist_ok=True)
    shutil.copytree(runtime/'SOURCES',output/'SOURCES',dirs_exist_ok=True)
    shutil.copy2(ROOT/'COPYING',output/'COPYING')
    with zipfile.ZipFile(output/'dos-tools.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['MEMSTAT.COM','FSVERIFY.EXE','DOSBENCH.EXE']:
            archive.write(tools/name,name)
        archive.writestr('README.TXT','Run in a writable DOS directory. MEMSTAT reports memory while the probe runs. FSVERIFY requires a fresh FSWORK directory. DOSBENCH 10 writes ten repeated workloads to stdout. Sources: https://github.com/RabbitRu/freedos-libretto/tree/libretto/scripts/libretto/dos\r\n')
        archive.write(ROOT/'COPYING','COPYING')
    (output/'fat32-tests.json').write_text(json.dumps(results,indent=2)+'\n')
    smoke = interactive_smoke(interactive,cpu,tools)
    with interactive.open('rb') as src, gzip.open(str(interactive)+'.gz','wb',compresslevel=9) as dst:
        shutil.copyfileobj(src,dst)
    interactive.unlink()
    summary = json.loads((output/'report.json').read_text())
    summary['fat32_validation'] = 'pass'
    summary['interactive_prompt_smoke'] = smoke
    summary['fat32_test_runs'] = len(results)
    summary['limitations'] = ['Game compatibility and DOS extenders are not tested yet.', 'Memory is measured while MEMSTAT runs under FreeCOM.', 'Full-volume and injected I/O error cases are not tested yet.', 'QEMU timings are not real Libretto performance measurements.']
    (output/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Do not ship temporary CI-only images and copies of the compiler output.
    shutil.rmtree(tools)

if __name__ == '__main__':
    main()

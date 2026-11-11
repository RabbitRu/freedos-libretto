#!/usr/bin/env python3
"""Scout conservative Watcom settings against the same memory-optimized source.

Two samples per workload screen candidates. The selected setting still needs the
normal ten-sample comparison and all filesystem/boot checks before acceptance.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import images

ROOT = Path(__file__).resolve().parents[2]
OPTIONS = [('size', '-os', ''), ('speed', '-ot', ''),
           ('scheduled-size', '-os -ob -or -ol', ''), ('scheduled', '-os -or', ''),
           ('hot-speed', '-os', '-ot -ob -or -ol'),
           ('scheduled-speed', '-ot -ob -or -ol', '')]


def main():
    cpu = sys.argv[1]
    assert cpu in ('486', 'pentium-mmx')
    package = ROOT/'_output'/f'libretto-{cpu}-fat32'
    output = package/'compiler'; output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, WATCOM=str(ROOT/'_watcom'), LIBRETTO_TUNE='4' if cpu=='486' else '5')
    env['PATH'] = str(ROOT/'_watcom/binl64')+os.pathsep+env['PATH']
    flags = ['COMPILER=owlinux', 'XCPU=386', 'XFAT=32', 'XUPX=', 'RM=rm -f']
    original = (package/'KERNEL.SYS').read_bytes()
    # Always rebuild the reference explicitly with -os, regardless of defaults.
    reports = []
    commit = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    try:
        for name, options, hot_options in OPTIONS:
            directory = output/name; directory.mkdir(exist_ok=True)
            build_env = dict(env, LIBRETTO_OPT=options)
            build_env.pop("LIBRETTO_HOT_OPT", None)
            if hot_options: build_env["LIBRETTO_HOT_OPT"] = hot_options
            try:
                with (directory/'build.log').open('wb') as log:
                    for target in ['clobber','all']:
                        images.run(['make',target]+flags, cwd=ROOT, env=build_env,
                                   stdout=log, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                text = (directory/'build.log').read_text(errors='replace')
                if 'Error! E2020: size of group TGROUP exceeds 64k' not in text: raise
                reports.append(dict(name=name, options=options, hot_options=hot_options,
                                    status='rejected_segment_overflow',
                                    error=next(l for l in text.splitlines() if 'Error! E2020:' in l)))
                print('COMPILER_VARIANT '+json.dumps(reports[-1]), flush=True)
                continue
            # Kernel entry assumes Watcom leaves high GPR halves alone.
            # Archive and check C disassembly for every successful setting.
            disassembly = directory/'disassembly'; disassembly.mkdir(exist_ok=True)
            for source in (ROOT/'kernel').glob('*.c'):
                obj = source.with_suffix('.obj')
                if not obj.exists(): continue
                listing = disassembly/(source.stem+'.txt')
                images.run(['wdis','-l='+str(listing),obj], stdout=subprocess.DEVNULL, env=env)
                assert not re.search(r'\b(eax|ebx|ecx|edx|esi|edi|ebp|esp|mm[0-7]|xmm\d+)\b',
                                     listing.read_text(), re.I), listing
            kernel = (ROOT/'bin/kwc38632.sys').read_bytes()
            (directory/'KERNEL.SYS').write_bytes(kernel)
            shutil.copy2(ROOT/'bin/kwc38632.map', directory/'kernel.map')
            if name == 'size': (output/'control.sys').write_bytes(kernel)
            (package/'KERNEL.SYS').write_bytes(kernel)
            compare_env = dict(env, LIBRETTO_BASELINE=commit, LIBRETTO_COMPARE_REPEATS='1',
                               LIBRETTO_CONTROL_KERNEL=str(output/'control.sys'),
                               LIBRETTO_COMPARISON_DIR=str(directory/'comparison'))
            with (directory/'compare.log').open('wb') as log:
                images.run(['python3', ROOT/'scripts/libretto/compare.py', cpu], cwd=ROOT,
                           env=compare_env, stdout=log, stderr=subprocess.STDOUT)
            comparison = json.loads((directory/'comparison/comparison.json').read_text())
            reports.append(dict(name=name, options=options, hot_options=hot_options, status="pass",
                                kernel_bytes=len(kernel), high_gpr_mmx_uses_in_c=False,
                                kernel_sha256=hashlib.sha256(kernel).hexdigest(),
                                calibration=comparison['calibration'],
                                memory=comparison['memory_reports'], summaries=comparison['summaries']))
            print('COMPILER_VARIANT '+json.dumps(reports[-1]), flush=True)
    finally:
        (package/'KERNEL.SYS').write_bytes(original)
    report = dict(cpu=cpu, commit=commit, samples_per_variant=2, variants=reports,
                  fixed_abi='16-bit small model, Pascal helpers, -r -zp1 -j -zgf -zff',
                  limitations=['Scout results require full validation of the selected setting.',
                               'QEMU instruction counts are not CPU cycles or native timing.'])
    (output/'compiler.json').write_text(json.dumps(report,indent=2)+'\n')
    print('COMPILER_REPORT '+json.dumps(report),flush=True)


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Fetch explicit upstream DOS runtime releases and record every input hash."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / '_downloads' / 'runtime'
SPECS = [
    ('freecom', 'com086', 'English.zip', 'https://github.com/FDOS/freecom/releases/download/com086/English.zip', None, 'COMMAND.COM'),
    ('himemx', '3.40', 'HimemX340.zip', 'https://github.com/Baron-von-Riedesel/HimemX/releases/download/v3.40/HimemX340.zip', 'e6e9913f26aec2e264bf514ddd1910cde319122cafeeda1b46cc0756beae25f8', 'HIMEMX.EXE'),
    ('jemm', '5.86', 'JemmB_v586.zip', 'https://github.com/Baron-von-Riedesel/Jemm/releases/download/v5.86/JemmB_v586.zip', '94838a1836f94d95dcf84d250f7968dfca2eb6b5cfa7ac664d6e01f22f0d296e', 'JEMMEX.EXE'),
]

def main():
    target = Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, version, filename, url, expected, binary in SPECS:
        archive = CACHE / filename
        if not archive.exists():
            with urllib.request.urlopen(url, timeout=90) as response:
                data = response.read()
            archive.write_bytes(data)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if expected and digest != expected:
            raise ValueError(f'{name}: upstream archive hash mismatch')
        print(f'RUNTIME_ARCHIVE {name} {digest}', flush=True)
        with zipfile.ZipFile(archive) as z:
            members = [n for n in z.namelist() if Path(n.replace('\\', '/')).name.upper() == binary]
            if name == 'freecom':
                members = [n for n in members if n.replace('\\', '/').lower() == 'xmsswap/command.com']
            if len(members) != 1:
                raise ValueError(f'{name}: expected one {binary}; archive contains {z.namelist()}')
            content = z.read(members[0])
            (target / binary).write_bytes(content)
            docs = target / 'LICENSES' / name
            docs.mkdir(parents=True, exist_ok=True)
            for n in z.namelist():
                base = Path(n.replace('\\', '/')).name
                if base and any(k in base.lower() for k in ('license', 'copying', 'readme')):
                    (docs / base).write_bytes(z.read(n))
        item = dict(name=name, version=version, url=url, archive_sha256=digest,
                    binary=binary, archive_member=members[0], binary_sha256=hashlib.sha256(content).hexdigest())
        manifest.append(item)
        print(json.dumps(item), flush=True)
    (target / 'RUNTIME.JSON').write_text(json.dumps(manifest, indent=2) + '\n')

if __name__ == '__main__':
    main()

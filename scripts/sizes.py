"""Per-package size of the built rootfs, largest first, so trimming is not guesswork.

Reads the apk database in the image's root directory and sums each package's
files; `xz_bytes` compresses them together the way squashfs roughly does.
"""
import json
import lzma
from pathlib import Path
import sys

root = Path(sys.argv[1])
rootfs = list((root / 'source/build_dir').glob('target-*/root-qualcommax'))
if len(rootfs) != 1:
    raise SystemExit(f'Expected one rootfs directory, found {len(rootfs)}')
rootfs = rootfs[0]

# Independent of the package database's format: the biggest single files.
files = sorted((p for p in rootfs.rglob('*') if p.is_file() and not p.is_symlink()),
               key=lambda p: p.stat().st_size, reverse=True)
print('largest files:')
for p in files[:30]:
    print(f'{p.stat().st_size:11} {p.relative_to(rootfs)}')

packages, name, folder = {}, None, ''
for line in (rootfs / 'lib/apk/db/installed').read_text().splitlines():
    if line.startswith('P:'):
        name, folder = line[2:], ''
        packages[name] = []
    elif line.startswith('F:'):
        folder = line[2:]
    elif line.startswith('R:') and name:
        packages[name].append(rootfs / folder / line[2:])

rows = []
for name, files in packages.items():
    data = b''.join(p.read_bytes() for p in files if p.is_file() and not p.is_symlink())
    rows.append(dict(package=name, files=len(files), bytes=len(data),
                     xz_bytes=len(lzma.compress(data, preset=6)) if data else 0))
rows.sort(key=lambda r: r['xz_bytes'], reverse=True)
(root / 'artifacts/package-sizes.json').write_text(json.dumps(rows, indent=1))
print(f"{'package':40} {'files':>6} {'bytes':>11} {'xz':>10}")
for r in rows[:40]:
    print(f"{r['package']:40} {r['files']:6} {r['bytes']:11} {r['xz_bytes']:10}")
print('total', sum(r['bytes'] for r in rows), 'bytes,', sum(r['xz_bytes'] for r in rows), 'xz')

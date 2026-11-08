"""sizes.py on a tiny fake build tree: python tests/test_sizes.py"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    rootfs = tmp / 'source/build_dir/target-aarch64_cortex-a53_musl/root-qualcommax'
    (rootfs / 'usr/bin').mkdir(parents=True)
    (rootfs / 'lib/apk/db').mkdir(parents=True)
    (tmp / 'artifacts').mkdir()
    (rootfs / 'usr/bin/big').write_bytes(bytes(range(256)) * 400)
    (rootfs / 'usr/bin/small').write_bytes(b'x' * 10)
    (rootfs / 'lib/apk/db/installed').write_text(
        'C:Q1abc\nP:bigpkg\nV:1-r1\nF:usr/bin\nR:big\n\nP:smallpkg\nV:1-r1\nF:usr/bin\nR:small\n\n')
    out = subprocess.run([sys.executable, str(here / 'scripts/sizes.py'), str(tmp)],
                         capture_output=True, text=True, check=True).stdout
    rows = json.loads((tmp / 'artifacts/package-sizes.json').read_text())
    assert [r['package'] for r in rows] == ['bigpkg', 'smallpkg'], rows
    assert rows[0]['bytes'] == 102400 and rows[1]['bytes'] == 10, rows
    assert 'usr/bin/big' in out.replace('\\', '/'), out
print('test_sizes OK')

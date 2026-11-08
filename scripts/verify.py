"""Fail when the build drifts from the frozen 2026-09-12 AX9000 image; never flashes."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

DEVICE = 'xiaomi_ax9000'
REFERENCE = 'reference/ax9000-2026-09-12.manifest'
# Left out on purpose (campus network code stays out of a public repo).
EXCLUDED = {'multidial'}
IMAGES = ['initramfs-factory.ubi', 'initramfs-uImage.itb',
          'squashfs-factory.ubi', 'squashfs-sysupgrade.bin']


def manifest(path):
    return dict(line.split(' - ', 1) for line in path.read_text().splitlines() if ' - ' in line)


def main():
    mode, root = sys.argv[1], Path(sys.argv[2])
    artifacts = root / 'artifacts'
    seed = (root / 'config.seed').read_text()
    cfg = (root / 'source/.config').read_text()
    wanted = set(re.findall(r'^CONFIG_(.+)=y$', seed, re.M))
    enabled = set(re.findall(r'^CONFIG_(.+)=y$', cfg, re.M))
    missing = sorted(wanted - enabled)
    forbidden = sorted(x for x in enabled if x.startswith('PACKAGE_') and x[8:] in EXCLUDED)
    devices = sorted(x for x in enabled if x.startswith('TARGET_') and '_DEVICE_' in x)
    report = dict(missing_after_defconfig=missing, forbidden=forbidden, selected_devices=devices)
    (artifacts / 'config-audit.json').write_text(json.dumps(report, indent=2))
    if missing or forbidden or devices != [f'TARGET_qualcommax_ipq807x_DEVICE_{DEVICE}']:
        raise SystemExit(json.dumps(report, indent=2))
    if mode == 'config':
        print('CONFIG_AUDIT_PASS', len(wanted), 'seed symbols kept')
        return
    target = root / 'source/bin/targets/qualcommax/ipq807x'
    manifests = list(target.glob(f'*{DEVICE}.manifest'))
    if len(manifests) != 1:
        raise SystemExit(f'Expected one {DEVICE} manifest, found {len(manifests)}')
    built = manifest(manifests[0])
    ref = {k: v for k, v in manifest(root / REFERENCE).items() if k not in EXCLUDED}
    diff = dict(
        missing=sorted(set(ref) - set(built)),
        extra=sorted(set(built) - set(ref)),
        version_changed={k: [ref[k], built[k]] for k in sorted(set(ref) & set(built)) if ref[k] != built[k]},
    )
    (artifacts / 'manifest-diff.json').write_text(json.dumps(diff, indent=2))
    print(json.dumps(diff, indent=2))
    # Every source and feed is pinned, so the package set must match exactly.
    if diff['missing'] or diff['extra']:
        raise SystemExit('Package set drifted from the 2026-09-12 image')
    fw = artifacts / 'firmware'
    fw.mkdir(exist_ok=True)
    for suffix in IMAGES:
        found = list(target.glob(f'*{DEVICE}-{suffix}'))
        if len(found) != 1:
            raise SystemExit(f'Missing or ambiguous image: {suffix}')
    for path in target.iterdir():
        if path.is_file() and (DEVICE in path.name or path.name in ['profiles.json', 'config.buildinfo', 'feeds.buildinfo', 'version.buildinfo', 'sha256sums']):
            shutil.copy2(path, fw / path.name)
    (fw / 'SHA256SUMS.local').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in sorted(fw.iterdir()) if p.is_file() and p.name != 'SHA256SUMS.local'))
    print('MANIFEST_AUDIT_PASS', len(built), 'packages; flashing is a separate, manual step')


if __name__ == '__main__':
    main()

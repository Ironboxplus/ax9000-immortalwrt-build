"""Fail on a missing package, a missing image or an image too big for a stock slot; never flashes."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile

DEVICE = 'xiaomi_ax9000-stock'
EXCLUDED = {'multidial'}  # campus network code stays out of a public repo
IMAGES = ['initramfs-factory.ubi', 'squashfs-sysupgrade.bin']

# Stock A/B layout: each of rootfs / rootfs_1 is 448 PEBs of 128 KiB. UBI keeps
# 40 PEBs for bad blocks (20 per 1024 of the 256 MiB chip, not of the
# partition) and 4 for its volume table and wear levelling; a LEB is the PEB
# minus two 2 KiB headers. kernel, rootfs and rootfs_data share that one UBI.
SLOT_BYTES = 448 * 128 * 1024
LEB = 128 * 1024 - 2 * 2048
USABLE_LEBS = 448 - 40 - 4
MIN_OVERLAY_BYTES = 4 * 1024 * 1024


def lebs(n):
    return -(-n // LEB)


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
    installed = {line.split(' - ')[0] for line in manifests[0].read_text().splitlines()}
    packages = {x[8:] for x in wanted if x.startswith('PACKAGE_')}
    absent = sorted(packages - installed)
    leaked = sorted(installed & EXCLUDED)
    if absent or leaked:
        raise SystemExit(f'Manifest mismatch: missing={absent}, forbidden={leaked}')
    # The local ath11k fix must be in the tree the shipped module was built
    # from (it adds no string of its own to the binary).
    ath11k = list((root / 'source/build_dir').glob('target-*/linux-*/mac80211-*/backports-*/drivers/net/wireless/ath/ath11k'))
    if len(ath11k) != 1 or not (ath11k[0] / 'ath11k.ko').exists():
        raise SystemExit(f'Expected one built ath11k tree with ath11k.ko, found {len(ath11k)}')
    if 'from the addr rhash only' not in (ath11k[0] / 'peer.c').read_text():
        raise SystemExit('ath11k was built without the band-migration fix')

    found = {}
    for suffix in IMAGES:
        hits = list(target.glob(f'*{DEVICE}-{suffix}'))
        if len(hits) != 1:
            raise SystemExit(f'Missing or ambiguous image: {suffix}')
        found[suffix] = hits[0]
    with tarfile.open(found['squashfs-sysupgrade.bin']) as archive:
        members = archive.getmembers()
        kernels = [m for m in members if m.name.endswith('/kernel')]
        roots = [m for m in members if m.name.endswith('/root')]
        if len(kernels) != 1 or len(roots) != 1:
            raise SystemExit('Cannot inspect kernel/root sizes')
    used = lebs(kernels[0].size) + lebs(roots[0].size)
    sizes = dict(
        kernel_bytes=kernels[0].size, rootfs_bytes=roots[0].size,
        slot_usable_lebs_estimate=USABLE_LEBS, used_lebs=used,
        overlay_left_bytes=(USABLE_LEBS - used) * LEB,
        initramfs_factory_bytes=found['initramfs-factory.ubi'].stat().st_size,
        slot_bytes=SLOT_BYTES, device_boot_tested=False, flash_authorized_by_build=False,
    )
    (artifacts / 'stock-slot-report.json').write_text(json.dumps(sizes, indent=2))
    print(json.dumps(sizes, indent=2))
    if sizes['overlay_left_bytes'] < MIN_OVERLAY_BYTES:
        raise SystemExit('sysupgrade image leaves under 4 MiB of overlay in a stock slot')
    if sizes['initramfs_factory_bytes'] > SLOT_BYTES:
        raise SystemExit('initramfs-factory.ubi is larger than a stock slot')

    fw = artifacts / 'firmware'
    fw.mkdir(exist_ok=True)
    for path in target.iterdir():
        if path.is_file() and (DEVICE in path.name or path.name in ['profiles.json', 'config.buildinfo', 'feeds.buildinfo', 'version.buildinfo', 'sha256sums']):
            shutil.copy2(path, fw / path.name)
    (fw / 'SHA256SUMS.local').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in sorted(fw.iterdir()) if p.is_file() and p.name != 'SHA256SUMS.local'))
    print('MANIFEST_AUDIT_PASS', len(packages), 'packages; flashing is a separate, manual step')


if __name__ == '__main__':
    main()

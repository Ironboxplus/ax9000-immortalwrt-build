"""Offline checks of the two AX9000 stock-layout images before they go near the router.

- squashfs-factory.ubi: written with ubiformat into the inactive stock slot. UBI
  geometry matches the NAND (128 KiB PEB, 2 KiB page), it fits a 56 MiB slot,
  volumes are kernel/rootfs/rootfs_data with IDs 0/1/2 (the -stock DT boots
  root=/dev/ubiblock0_1), and kernel/rootfs carry the sysupgrade payloads.
- squashfs-sysupgrade.bin: sysupgrade tar for that board, kernel FIT with the
  stock device tree, squashfs root, and fwtool metadata naming the device.

Both kernels must fit the stock RA70 U-Boot memory window: the FIT is read to
0x44000000 and unpacked to its load address. Below 0x41000000 is the NSS no-map
region (nss@40000000, 16 MiB; NSS firmware is loaded there), so the kernel,
including BSS, must lie in [0x41000000, 0x44000000).
usage: python verify_images.py FIRMWARE_DIR
"""
import io
import json
import gzip
from pathlib import Path
import struct
import sys
import tarfile

import fdt
from ubireader import ubi_io
from ubireader.ubi import ubi as ubi_obj
from ubireader.utils import guess_peb_size

SLOT_BYTES = 0x3800000
COMPAT = 'xiaomi,ax9000-stock'
NSS_REGION_END = 0x41000000      # nss@40000000 no-map, 16 MiB
STOCK_UBOOT_FIT_ADDR = 0x44000000
TZAPP_REGION = 0x4a400000        # first reserved region above the FIT buffer
VOLUME_IDS = {'kernel': 0, 'rootfs': 1, 'rootfs_data': 2}
fw = Path(sys.argv[1])
factory = next(fw.glob('*ax9000-stock-squashfs-factory.ubi'))
sysupgrade = next(fw.glob('*ax9000-stock-squashfs-sysupgrade.bin'))
report, failures = {}, []


def check(name, ok, detail=''):
    report[name] = dict(ok=bool(ok), detail=detail)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        failures.append(name)


def property_bytes(prop):
    """Normalize fdt.PropBytes and fdt.PropWords across fdt package versions."""
    if isinstance(prop.data, (bytes, bytearray)):
        return bytes(prop.data)
    return b''.join(struct.pack('>I', word) for word in prop.data)


def fit_dt_compatibles(blob):
    """Compatible strings of the device trees referenced by the FIT's configurations."""
    tree = fdt.parse_dtb(blob)
    confs = tree.get_node('/configurations')
    default = confs.get_property('default').value
    out = {}
    for conf in confs.nodes:
        dt_name = conf.get_property('fdt').value
        dt_blob = property_bytes(tree.get_node(f'/images/{dt_name}').get_property('data'))
        out[conf.name] = fdt.parse_dtb(dt_blob).root.get_property('compatible').data
    return default, out


def fit_kernel_layout(blob):
    """Load/entry of the default kernel and where it ends in RAM once unpacked.

    The arm64 Image header gives text_offset and image_size, which includes BSS;
    the unpacked length alone undercounts the footprint.
    """
    tree = fdt.parse_dtb(blob)
    confs = tree.get_node('/configurations')
    default = confs.get_property('default').value
    conf = next(node for node in confs.nodes if node.name == default)
    image = tree.get_node(f"/images/{conf.get_property('kernel').value}")
    load = int(image.get_property('load').value)
    entry = int(image.get_property('entry').value)
    payload = property_bytes(image.get_property('data'))
    compression = image.get_property('compression').value
    kernel = gzip.decompress(payload) if compression == 'gzip' else payload
    if kernel[56:60] == b'ARM\x64':
        text_offset, image_size = struct.unpack_from('<QQ', kernel, 8)
        end = load + text_offset + max(image_size, len(kernel))
    else:
        end = load + len(kernel)
    return load, entry, end


def check_kernel_window(label, blob):
    load, entry, end = fit_kernel_layout(blob)
    check(f'{label} kernel loads above the NSS no-map region',
          load >= NSS_REGION_END and entry == load, f'load=0x{load:x} entry=0x{entry:x} floor=0x{NSS_REGION_END:x}')
    check(f'{label} kernel (with BSS) ends below the stock U-Boot FIT buffer',
          end <= STOCK_UBOOT_FIT_ADDR, f'end=0x{end:x} limit=0x{STOCK_UBOOT_FIT_ADDR:x}')
    fit_end = STOCK_UBOOT_FIT_ADDR + len(blob)
    check(f'{label} FIT read to 0x44000000 stays below the TZ apps region',
          fit_end <= TZAPP_REGION, f'fit={len(blob)} end=0x{fit_end:x} limit=0x{TZAPP_REGION:x}')


# squashfs-sysupgrade.bin
raw = sysupgrade.read_bytes()
with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
    members = {m.name.split('/', 1)[1]: m for m in tar.getmembers() if '/' in m.name}
    control = tar.extractfile(members['CONTROL']).read().decode()
    sys_kernel = tar.extractfile(members['kernel']).read()
    sys_root = tar.extractfile(members['root']).read()
check('sysupgrade CONTROL board', 'BOARD=xiaomi_ax9000-stock' in control, control.strip().replace('\n', ' '))
default, compat = fit_dt_compatibles(sys_kernel)
check('sysupgrade FIT default config has the stock DT',
      COMPAT in compat.get(default, []), f'default={default} {compat}')
check_kernel_window('sysupgrade', sys_kernel)
check('sysupgrade root is squashfs', sys_root[:4] == b'hsqs', repr(sys_root[:4]))
# fwtool metadata: JSON followed by a trailer at the end of the image
start = raw.rfind(b'{  "metadata_version"')
if start < 0:
    start = raw.rfind(b'{"metadata_version"')
meta = json.JSONDecoder().raw_decode(raw[start:].decode(errors='replace'))[0] if start >= 0 else {}
devices = meta.get('supported_devices', [])
check('sysupgrade metadata supports the stock board', COMPAT in devices, f'supported_devices={devices}')

# squashfs-factory.ubi
data = factory.read_bytes()
check('factory.ubi fits a stock slot', len(data) <= SLOT_BYTES, f'{len(data)} <= {SLOT_BYTES}')
peb = guess_peb_size(str(factory))
check('factory.ubi PEB is 128 KiB', peb == 0x20000, hex(peb))
# UBI EC header: magic, version, pad, ec(8), vid_hdr_offset, data_offset
vid_offset, data_offset = struct.unpack('>II', data[16:24])
check('factory.ubi VID header at 2048, data at 4096', (vid_offset, data_offset) == (2048, 4096),
      f'vid={vid_offset} data={data_offset}')
ubi = ubi_obj(ubi_io.ubi_file(str(factory), peb))
vols = dict(ubi.images[0].volumes)
ids = {name: vol.vol_id for name, vol in vols.items()}
check('factory.ubi volumes are kernel/rootfs/rootfs_data = 0/1/2', ids == VOLUME_IDS, f'{ids}')
if 'rootfs_data' in vols:
    check('factory.ubi rootfs_data is autoresize', vols['rootfs_data'].vol_rec.flags & 1,
          f'flags={vols["rootfs_data"].vol_rec.flags}')
if 'kernel' in vols:
    ubi_kernel = b''.join(vols['kernel'].reader(ubi))
    check('factory.ubi kernel volume is the sysupgrade kernel', ubi_kernel[:len(sys_kernel)] == sys_kernel,
          f'{len(sys_kernel)} bytes')
    default, compat = fit_dt_compatibles(ubi_kernel)
    check('factory.ubi FIT default config has the stock DT',
          COMPAT in compat.get(default, []), f'default={default} {compat}')
    check_kernel_window('factory.ubi', ubi_kernel[:len(sys_kernel)])
if 'rootfs' in vols:
    ubi_root = b''.join(vols['rootfs'].reader(ubi))
    used = struct.unpack_from('<Q', sys_root, 40)[0]  # squashfs bytes_used; padding differs (00 vs ff)
    check('factory.ubi rootfs volume is the sysupgrade squashfs', ubi_root[:used] == sys_root[:used],
          f'bytes_used={used}')

(fw.parent / 'image-verification.json').write_text(json.dumps(report, indent=1))
print('ALL PASS' if not failures else f'FAILED: {failures}')
sys.exit(1 if failures else 0)

"""Offline checks of the two AX9000 stock-layout images before they go near the router.

- initramfs-factory.ubi: UBI geometry matches the NAND (128 KiB PEB, 2 KiB page),
  it fits a 56 MiB slot, and its 'kernel' volume is a FIT whose configurations
  carry the xiaomi,ax9000-stock device tree.
- squashfs-sysupgrade.bin: sysupgrade tar for that board, kernel FIT with the
  same device tree, squashfs root, and fwtool metadata naming the device.
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
STOCK_UBOOT_FIT_ADDR = 0x44000000
STOCK_KERNEL_LOADADDR = 0x40000000
fw = Path(sys.argv[1])
initramfs = next(fw.glob('*ax9000-stock-initramfs-factory.ubi'))
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


def fit_kernel_load_safety(blob):
    """Check the large initramfs against the stock RA70 U-Boot load window."""
    tree = fdt.parse_dtb(blob)
    confs = tree.get_node('/configurations')
    default = confs.get_property('default').value
    conf = next(node for node in confs.nodes if node.name == default)
    kernel_name = conf.get_property('kernel').value
    image = tree.get_node(f'/images/{kernel_name}')
    load = int(image.get_property('load').value)
    entry = int(image.get_property('entry').value)
    compression = image.get_property('compression').value
    payload = property_bytes(image.get_property('data'))
    uncompressed = gzip.decompress(payload) if compression == 'gzip' else payload
    end = load + len(uncompressed)
    return load, entry, len(uncompressed), end


# initramfs-factory.ubi
data = initramfs.read_bytes()
check('initramfs fits a stock slot', len(data) <= SLOT_BYTES, f'{len(data)} <= {SLOT_BYTES}')
peb = guess_peb_size(str(initramfs))
check('initramfs PEB is 128 KiB', peb == 0x20000, hex(peb))
ufile = ubi_io.ubi_file(str(initramfs), peb)
ubi = ubi_obj(ufile)
vols = dict(ubi.images[0].volumes)
# UBI EC header: magic, version, pad, ec(8), vid_hdr_offset, data_offset
vid_offset, data_offset = struct.unpack('>II', data[16:24])
check('initramfs VID header at 2048, data at 4096', (vid_offset, data_offset) == (2048, 4096),
      f'vid={vid_offset} data={data_offset}')
check('initramfs has a kernel volume', 'kernel' in vols, f'volumes={sorted(vols)}')
kernel = b''.join(vols['kernel'].reader(ubi))
default, compat = fit_dt_compatibles(kernel)
check('initramfs FIT default config has the stock DT',
      COMPAT in compat.get(default, []), f'default={default} {compat}')
load, entry, unpacked, end = fit_kernel_load_safety(kernel)
check('initramfs FIT load address is the stock-safe address',
      (load, entry) == (STOCK_KERNEL_LOADADDR, STOCK_KERNEL_LOADADDR),
      f'load=0x{load:x} entry=0x{entry:x}')
check('initramfs kernel does not overwrite the stock U-Boot FIT buffer',
      end <= STOCK_UBOOT_FIT_ADDR,
      f'unpacked={unpacked} end=0x{end:x} limit=0x{STOCK_UBOOT_FIT_ADDR:x}')

# squashfs-sysupgrade.bin
raw = sysupgrade.read_bytes()
with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
    members = {m.name.split('/', 1)[1]: m for m in tar.getmembers() if '/' in m.name}
    control = tar.extractfile(members['CONTROL']).read().decode()
    sys_kernel = tar.extractfile(members['kernel']).read()
    root_head = tar.extractfile(members['root']).read(4)
check('sysupgrade CONTROL board', 'BOARD=xiaomi_ax9000-stock' in control, control.strip().replace('\n', ' '))
default, compat = fit_dt_compatibles(sys_kernel)
check('sysupgrade FIT default config has the stock DT',
      COMPAT in compat.get(default, []), f'default={default} {compat}')
load, entry, unpacked, end = fit_kernel_load_safety(sys_kernel)
check('sysupgrade FIT load address is the stock-safe address',
      (load, entry) == (STOCK_KERNEL_LOADADDR, STOCK_KERNEL_LOADADDR),
      f'load=0x{load:x} entry=0x{entry:x}')
check('sysupgrade kernel does not overwrite the stock U-Boot FIT buffer',
      end <= STOCK_UBOOT_FIT_ADDR,
      f'unpacked={unpacked} end=0x{end:x} limit=0x{STOCK_UBOOT_FIT_ADDR:x}')
check('sysupgrade root is squashfs', root_head == b'hsqs', repr(root_head))
# fwtool metadata: JSON followed by a trailer at the end of the image
start = raw.rfind(b'{  "metadata_version"')
if start < 0:
    start = raw.rfind(b'{"metadata_version"')
meta = json.JSONDecoder().raw_decode(raw[start:].decode(errors='replace'))[0] if start >= 0 else {}
devices = meta.get('supported_devices', [])
check('sysupgrade metadata supports the stock board', COMPAT in devices or 'xiaomi,ax9000-stock' in devices,
      f'supported_devices={devices}')

(fw.parent / 'image-verification.json').write_text(json.dumps(report, indent=1))
print('ALL PASS' if not failures else f'FAILED: {failures}')
sys.exit(1 if failures else 0)

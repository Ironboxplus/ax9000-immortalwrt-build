"""verify.py config: seed symbols must stay set (=m ones at least as modules),
'# ... is not set' ones must stay off.
python tests/test_verify_config.py"""
from pathlib import Path
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent.parent
DEVICE = 'CONFIG_TARGET_qualcommax_ipq807x_DEVICE_xiaomi_ax9000-stock=y\n'
SEED = DEVICE + 'CONFIG_PACKAGE_easytier=y\n# CONFIG_EASYTIER_INCLUDE_WEBCONSOLE is not set\nCONFIG_PACKAGE_fping=m\n'


def run(resolved):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'source').mkdir()
        (tmp / 'artifacts').mkdir()
        (tmp / 'config.seed').write_text(SEED)
        (tmp / 'source/.config').write_text(resolved)
        return subprocess.run([sys.executable, str(here / 'scripts/verify.py'), 'config', str(tmp)],
                              capture_output=True, text=True)


BASE = DEVICE + 'CONFIG_PACKAGE_easytier=y\n'
ok = run(BASE + '# CONFIG_EASYTIER_INCLUDE_WEBCONSOLE is not set\nCONFIG_PACKAGE_fping=m\n')
assert ok.returncode == 0 and 'CONFIG_AUDIT_PASS' in ok.stdout, ok.stdout + ok.stderr
in_image = run(BASE + 'CONFIG_PACKAGE_fping=y\n')
assert in_image.returncode == 0, in_image.stdout + in_image.stderr
back_on = run(BASE + 'CONFIG_EASYTIER_INCLUDE_WEBCONSOLE=y\nCONFIG_PACKAGE_fping=m\n')
assert back_on.returncode != 0 and 'EASYTIER_INCLUDE_WEBCONSOLE' in back_on.stderr, back_on.stderr
dropped = run(DEVICE + 'CONFIG_PACKAGE_fping=m\n')
assert dropped.returncode != 0 and 'PACKAGE_easytier' in dropped.stderr, dropped.stderr
no_module = run(BASE)
assert no_module.returncode != 0 and 'PACKAGE_fping' in no_module.stderr, no_module.stderr
print('test_verify_config OK')

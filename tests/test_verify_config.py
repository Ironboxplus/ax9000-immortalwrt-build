"""verify.py config: seed symbols must stay set, '# ... is not set' ones must stay off.
python tests/test_verify_config.py"""
from pathlib import Path
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent.parent
DEVICE = 'CONFIG_TARGET_qualcommax_ipq807x_DEVICE_xiaomi_ax9000-stock=y\n'
SEED = DEVICE + 'CONFIG_PACKAGE_easytier=y\n# CONFIG_EASYTIER_INCLUDE_WEBCONSOLE is not set\n'


def run(resolved):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'source').mkdir()
        (tmp / 'artifacts').mkdir()
        (tmp / 'config.seed').write_text(SEED)
        (tmp / 'source/.config').write_text(resolved)
        return subprocess.run([sys.executable, str(here / 'scripts/verify.py'), 'config', str(tmp)],
                              capture_output=True, text=True)


ok = run(DEVICE + 'CONFIG_PACKAGE_easytier=y\n# CONFIG_EASYTIER_INCLUDE_WEBCONSOLE is not set\n')
assert ok.returncode == 0 and 'CONFIG_AUDIT_PASS' in ok.stdout, ok.stdout + ok.stderr
back_on = run(DEVICE + 'CONFIG_PACKAGE_easytier=y\nCONFIG_EASYTIER_INCLUDE_WEBCONSOLE=y\n')
assert back_on.returncode != 0 and 'EASYTIER_INCLUDE_WEBCONSOLE' in back_on.stderr, back_on.stderr
dropped = run(DEVICE)
assert dropped.returncode != 0 and 'PACKAGE_easytier' in dropped.stderr, dropped.stderr
print('test_verify_config OK')

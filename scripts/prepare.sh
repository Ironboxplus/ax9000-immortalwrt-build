#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(pwd)
mkdir -p artifacts
source_url=$(python3 -c 'import json; print(json.load(open("source.lock.json"))["repository"])')
source_sha=$(python3 -c 'import json; print(json.load(open("source.lock.json"))["commit"])')
# source/ may already exist: the dl/ and .ccache/ caches are restored into it.
git init source
git -C source remote add origin "$source_url"
git -C source fetch --depth=1 origin "$source_sha"
git -C source checkout --detach FETCH_HEAD
test "$(git -C source rev-parse HEAD)" = "$source_sha"
cp feeds.conf source/feeds.conf.default
cd source
./scripts/feeds update -a 2>&1 | tee "$repo_dir/artifacts/feeds-update.log"
./scripts/feeds install -a 2>&1 | tee "$repo_dir/artifacts/feeds-install.log"
# Prefer the explicitly locked iStore and EasyTier feeds over any duplicate recipe.
./scripts/feeds install -a -f -p istore
./scripts/feeds install -a -f -p easytier
python3 - "$repo_dir" <<'PY'
import hashlib, json, pathlib, re, subprocess, sys, urllib.request
root = pathlib.Path(sys.argv[1])
lock = json.loads((root / 'source.lock.json').read_text())
provenance = {'source': lock, 'feeds': {}}
# feeds.conf pins every feed as src-git <name> <url>^<sha>; check what was checked out.
for line in (root / 'feeds.conf').read_text().splitlines():
    m = re.match(r'^src-git\s+(\S+)\s+\S+\^([0-9a-f]{40})$', line.strip())
    if not m:
        continue
    name, sha = m.groups()
    actual = subprocess.check_output(['git', '-C', f'feeds/{name}', 'rev-parse', 'HEAD'], text=True).strip()
    if actual != sha:
        raise SystemExit(f'Feed revision mismatch: {name} {actual} != {sha}')
    provenance['feeds'][name] = actual
# EasyTier's upstream recipe downloads a release ZIP during Build/Prepare.
# Populate its expected build directory from the SHA256-locked official asset.
version = lock['easytier_version']
url = f'https://github.com/EasyTier/EasyTier/releases/download/v{version}/easytier-linux-aarch64-v{version}.zip'
archive = pathlib.Path('dl') / f'easytier-linux-aarch64-v{version}.zip'
archive.parent.mkdir(exist_ok=True)
if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != lock['easytier_archive_sha256']:
    urllib.request.urlretrieve(url, archive)
if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['easytier_archive_sha256']:
    raise SystemExit('EasyTier official archive SHA256 mismatch')
provenance['easytier_archive'] = lock['easytier_archive_sha256']
recipe = pathlib.Path('feeds/easytier/easytier/Makefile')
text = recipe.read_text()
old = 'wget https://github.com/EasyTier/EasyTier/releases/download/v$(PKG_VERSION)/$(PKG_NAME)-linux-$(APP_ARCH)-v$(PKG_VERSION).zip -O $(PKG_BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION).zip;'
new = 'cp "$(DL_DIR)/easytier-linux-aarch64-v$(PKG_VERSION).zip" "$(PKG_BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION).zip";'
if text.count(old) != 1:
    raise SystemExit('Locked EasyTier recipe download statement changed')
recipe.write_text(text.replace(old, new))
provenance['easytier_recipe_sha256'] = hashlib.sha256(recipe.read_bytes()).hexdigest()
(root / 'artifacts/provenance.json').write_text(json.dumps(provenance, indent=2))
PY
# feeds update/install may invoke Kconfig before feed metadata exists and discard
# package selections. Apply the requested seed AFTER all feeds are installed.
cp "$repo_dir/config.seed" .config
make defconfig 2>&1 | tee "$repo_dir/artifacts/defconfig.log"
cp .config "$repo_dir/artifacts/config.resolved"
cp feeds.conf.default "$repo_dir/artifacts/feeds.conf"
cp "$repo_dir/source.lock.json" "$repo_dir/config.seed" "$repo_dir/artifacts/"
python3 "$repo_dir/scripts/verify.py" config "$repo_dir"

#!/usr/bin/env bash
set -euo pipefail
repo_dir=$(pwd)
mkdir -p artifacts
source_url=$(python3 -c 'import json; print(json.load(open("source.json"))["repository"])')
source_branch=$(python3 -c 'import json; print(json.load(open("source.json"))["branch"])')
# Follows the branch head; the commit actually built is recorded in provenance.json.
# source/ may already exist: the dl/ and .ccache/ caches are restored into it.
git init source
git -C source remote add origin "$source_url"
git -C source fetch --depth=1 origin "$source_branch"
git -C source checkout --detach FETCH_HEAD
# ccache's default compiler_check is the compiler's mtime, and every run builds
# the cross toolchain afresh, so no target object would ever hit across runs.
# Key on what the compiler reports about itself instead.
mkdir -p source/.ccache
printf 'compiler_check = %%compiler%% -v\n' > source/.ccache/ccache.conf
CCACHE_DIR=source/.ccache ccache -z
# The upstream feeds (unpinned, as upstream ships them) plus ours.
cat source/feeds.conf.default feeds.conf > source/feeds.conf.default.new
mv source/feeds.conf.default.new source/feeds.conf.default
cp -a files source/
chmod +x source/files/etc/uci-defaults/* source/files/usr/sbin/ax9000-wifi-setup
# Local fixes; each patch header explains why. git apply fails loudly when
# upstream moves under them.
for p in patches/target/*.patch; do
	git -C source apply --verbose "$repo_dir/$p"
done
cp patches/mac80211/nss/ath11k/*.patch source/package/kernel/mac80211/patches/nss/ath11k/
cp patches/qca-nss-ecm/*.patch source/package/qca-nss/qca-nss-ecm/patches/
# libffi moved from the packages feed into core on 2026-10-19; a source tree
# older than that combined with the current feed has it nowhere. Take the core
# recipe from ImmortalWrt until the source tree carries its own.
libffi_repo=https://github.com/immortalwrt/immortalwrt.git
libffi_commit=1c2d58530e7dc037db5d1db781de6bf259c90a95
if [ ! -e source/package/libs/libffi ]; then
	git init -q libffi-src
	git -C libffi-src fetch -q --depth=1 "$libffi_repo" "$libffi_commit"
	git -C libffi-src archive FETCH_HEAD package/libs/libffi | tar -x -C source
	rm -rf libffi-src
	echo "$libffi_repo $libffi_commit" > artifacts/libffi-backfill.txt
fi
cd source
./scripts/feeds update -a 2>&1 | tee "$repo_dir/artifacts/feeds-update.log"
./scripts/feeds install -a 2>&1 | tee "$repo_dir/artifacts/feeds-install.log"
# Prefer our feeds' recipes over any duplicate in the upstream feeds.
./scripts/feeds install -a -f -p istore
./scripts/feeds install -a -f -p easytier
./scripts/feeds install -a -f -p sqm_scripts_nss
./scripts/feeds install -a -f -p cakeautorate
python3 - "$repo_dir" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
head = lambda path: subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
provenance = {
    'source': dict(json.loads((root / 'source.json').read_text()), commit=head('.')),
    'feeds': {p.name: head(p) for p in sorted(pathlib.Path('feeds').iterdir()) if (p / '.git').exists()},
    'local_patches': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted((root / 'patches').rglob('*.patch'))},
}
(root / 'artifacts/provenance.json').write_text(json.dumps(provenance, indent=2))
print(json.dumps(provenance, indent=2))
PY
# feeds update/install may invoke Kconfig before feed metadata exists and discard
# package selections. Apply the requested seed AFTER all feeds are installed.
cp "$repo_dir/config.seed" .config
make defconfig 2>&1 | tee "$repo_dir/artifacts/defconfig.log"
cp .config "$repo_dir/artifacts/config.resolved"
cp feeds.conf.default "$repo_dir/artifacts/feeds.conf"
cp "$repo_dir/source.json" "$repo_dir/config.seed" "$repo_dir/artifacts/"
python3 "$repo_dir/scripts/verify.py" config "$repo_dir"

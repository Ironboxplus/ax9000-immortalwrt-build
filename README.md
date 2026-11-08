# Xiaomi AX9000 — qosmio NSS firmware build

Rebuilds, on GitHub Actions, the AX9000 image first built locally on
2026-09-12, with every input pinned:

- source: `qosmio/openwrt-ipq` `25.12-nss` @ `d6848fa` (`source.lock.json`)
- feeds: each pinned to a commit in `feeds.conf`; `prepare.sh` checks the
  checked-out revisions
- packages: `config.seed`, identical to that build's seed except that the
  campus-network `multidial` package is left out (it is installed separately)
- EasyTier 2.6.4: the release ZIP the recipe would `wget` is fetched once and
  checked against the SHA256 in `source.lock.json`

`scripts/verify.py` fails the run if `make defconfig` drops any seed symbol, or
if the image's package list differs from `reference/ax9000-2026-09-12.manifest`
(minus `multidial`). Version differences are listed in `manifest-diff.json`.

Run it with **Actions → Build AX9000 → Run workflow**. The artifact contains
`firmware/` (images, buildinfo, `SHA256SUMS.local`), the matching packages and
the logs; it is kept for 2 days.

A successful build is not a flashing go-ahead. Flashing this device is a
separate, manual procedure (stock layout checks, initramfs first).

# Xiaomi AX9000 — ImmortalWrt (VIKINGYFY) with traditional NSS, stock layout

Builds `xiaomi_ax9000-stock` on GitHub Actions: the Xiaomi U-Boot and its A/B
`rootfs` / `rootfs_1` slots stay as they are; nothing here touches U-Boot or
the partition table.

- source: `VIKINGYFY/immortalwrt` branch `main` (`source.json`), the line that
  keeps the traditional NSS stack (nss-drv, ECM, NSS qdiscs). Its default
  `owrt` branch replaced that stack with a new PPE driver and is not used.
- feeds: upstream's `feeds.conf.default` plus iStore, EasyTier and
  sqm-scripts-nss (`feeds.conf`). Source and feeds follow their branches; the
  commits a run used are in `provenance.json` in its artifact.
- packages: `config.seed`, the 2026-09-12 package set without the campus
  `multidial` package, which is installed separately.
- local patches:
  - `patches/target/0001-*`: produce `initramfs-factory.ubi` for the stock
    profile (upstream leaves `ARTIFACTS` empty), the first-stage image
    written to the inactive slot;
  - `patches/mac80211/nss/ath11k/999-*`: keep the right peer when a station
    changes band (see the patch header).
- first boot (`files/`): LAN 192.168.20.1/24, WAN DHCP; the three SSIDs are
  laid out on the radios picked by PCI path (QCN9074 for Game, QCA9887 off)
  but stay off, because the image carries no Wi-Fi password. Over the wired
  LAN run `ax9000-wifi-setup`; it reads the password without echo and turns
  them on.

`scripts/verify.py` fails the run if `make defconfig` drops a seed symbol, a
seed package is missing from the image, the ath11k fix did not reach the
built tree, or the sysupgrade image leaves under 4 MiB of overlay in a stock
slot (`stock-slot-report.json`).

Run it with **Actions → Build AX9000 → Run workflow**. Artifacts are kept for
2 days. A successful build is not a flashing go-ahead: flashing is a separate,
manual two-stage procedure (initramfs into the inactive slot first).

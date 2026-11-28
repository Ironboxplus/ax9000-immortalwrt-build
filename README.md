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
- no initramfs (2026-11-28). The stock RA70 U-Boot reads the FIT to
  0x44000000 and unpacks the kernel to its load address; below 0x41000000 is
  the NSS no-map region. With an initramfs the kernel unpacked to ~52 MB and
  overwrote the FIT (U-Boot resets before Linux, no slot fallback: the
  2026-11-25 boot loop); moving it to 0x40000000 put it in the NSS region.
  The non-initramfs kernel is ~15 MB. `squashfs-factory.ubi` (UBI volumes
  kernel/rootfs/rootfs_data = 0/1/2, what `root=/dev/ubiblock0_1` of the
  -stock DT expects) is written into the inactive slot from the stock system.
- local patches:
  - `patches/mac80211/nss/ath11k/999-*`: keep the right peer when a station
    changes band; print every PDEV_ERRS/WHAL_TX htt_stats field (both ported
    from the Arthur build, see the patch headers). `CONFIG_PACKAGE_ATH_DEBUG`
    compiles `ath11k_dbg()` in so the `debug_mask` module parameter works.
    The Arthur crash-recovery VAP-delete patch is deliberately not ported: it
    turned a firmware crash recovery into a full reboot there.
- `files/etc/sysctl.d/99-ax9000-netlink.conf`: rmem_max 1 MiB so nlbwmon's
  netlink dumps do not overflow.
- first boot (`files/`): LAN 192.168.20.1/24, WAN DHCP; the three SSIDs are
  laid out on the radios picked by PCI path (QCN9074 for Game, QCA9887 off)
  but stay off, because the image carries no Wi-Fi password. Over the wired
  LAN run `ax9000-wifi-setup`; it reads the password without echo and turns
  them on.

`scripts/verify.py` fails the run if `make defconfig` drops a seed symbol, a
seed package is missing from the image, the ath11k fix did not reach the
built tree, or the sysupgrade image leaves under 4 MiB of overlay in a stock
slot (`stock-slot-report.json`). `scripts/verify_images.py` checks the
factory.ubi volume layout and payloads, and that both kernels (BSS included)
sit in [0x41000000, 0x44000000).

Run it with **Actions → Build AX9000 → Run workflow**. Artifacts are kept for
2 days. A successful build is not a flashing go-ahead: flashing is a separate,
manual step (factory.ubi into the inactive slot from the stock system).

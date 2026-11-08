# Shared by /etc/uci-defaults/99-ax9000-wireless and /usr/sbin/ax9000-wifi-setup.
# Radios are told apart by hardware, never by radioN numbering:
#   PCIe 0000:01:00.0  QCN9074  -> 5 GHz Game SSID
#   PCIe 0001:01:00.0  QCA9887  -> the 1x1 IoT radio, kept off
#   IPQ8074 AHB radios -> the 2.4 GHz and the normal 5 GHz SSIDs

AX9000_SSID_2G=Xiaomi_87A4
AX9000_SSID_5G=Xiaomi_87A4_5G
AX9000_SSID_GAME=Xiaomi_87A4_5G_Game

# Sets ax9000_2g, ax9000_5g, ax9000_game and ax9000_iot to wifi-device
# section names. Returns 1 if any of the four is missing.
ax9000_wifi_map() {
	ax9000_2g= ax9000_5g= ax9000_game= ax9000_iot=
	local dev band path
	for dev in $(uci show wireless 2>/dev/null | sed -n "s/^wireless\.\([^.=]*\)=wifi-device$/\1/p"); do
		band=$(uci -q get "wireless.$dev.band" || true)
		path=$(uci -q get "wireless.$dev.path" || true)
		case "$path" in
		*0000:01:00.0*) ax9000_game=$dev ;;
		*0001:01:00.0*) ax9000_iot=$dev ;;
		*)
			[ "$band" = 2g ] && ax9000_2g=$dev
			[ "$band" = 5g ] && ax9000_5g=$dev
			;;
		esac
	done
	[ -n "$ax9000_2g" ] && [ -n "$ax9000_5g" ] && [ -n "$ax9000_game" ] && [ -n "$ax9000_iot" ]
}

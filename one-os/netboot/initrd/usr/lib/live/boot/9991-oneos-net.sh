#!/bin/sh
# one-os: patient Ethernet selection for network boots (overrides live-boot's Select_eth_device).
#
# netboot/server.py serves this directory as a second initrd (/live/oneos-net.cpio) after the
# home base's own; live-boot sources /lib/live/boot/*.sh in order, so this definition wins.
#
# Why: live-boot waits 15 s for a cable link with one NIC and only ~5 s with two or more (a second
# NIC, or Wi-Fi), then sets the link down ("Link is Down") and never sends DHCP. 2.5 GbE chips
# (Realtek RTL8125, Intel I225/I226) routinely take longer than that to renegotiate after the
# firmware hands them over. Here: prefer the NIC that PXE-booted (oneos.mac=, from iPXE), wait up
# to oneos.linkwait= seconds (default 90) for its link, and on failure show why on screen.

# The monitor is the console (console=tty0 last); copy our lines to serial for the test harness.
_say ()
{
	echo "$*"
	[ -w /dev/ttyS0 ] && echo "$*" > /dev/ttyS0 2>/dev/null
	return 0
}

Select_eth_device ()
{
	[ -n "$FETCH$NETBOOT$HTTPFS$FTPFS" ] || grep -qs '^BOOT=nfs' /conf/initramfs.conf || return 0

	modprobe -q af_packet
	udevadm trigger
	udevadm settle

	_wait=90 _mac=""
	# shellcheck disable=SC2013  # words, not lines
	for _arg in $(cat /proc/cmdline)
	do
		case "$_arg" in
			oneos.linkwait=*) _wait="${_arg#oneos.linkwait=}" ;;
			oneos.mac=*) _mac=$(echo "${_arg#oneos.mac=}" | tr 'A-F' 'a-f' | tr - :) ;;
		esac
	done

	_say "one-os: looking for the network card${_mac:+ $_mac} (up to ${_wait} s for a link)"

	# Network drivers can register after udev settles (firmware loading): give them 20 s.
	_ifs="" _n=0
	while [ $_n -lt 20 ]
	do
		_ifs=""
		for _d in /sys/class/net/*
		do
			_i=${_d##*/}
			# skip loopback and wireless (live-boot can't join Wi-Fi anyway)
			[ "$_i" = lo ] || [ -d "$_d/wireless" ] || [ -d "$_d/phy80211" ] && continue
			_ifs="$_ifs $_i"
		done
		[ -n "$_ifs" ] && break
		sleep 1; _n=$((_n + 1))
	done
	if [ -z "$_ifs" ]
	then
		_say "one-os: no wired network card found — its driver may be missing from kernel $(uname -r)."
		return 0
	fi

	# The PXE card first; the others are a fallback.
	_pref=""
	if [ -n "$_mac" ]
	then
		for _i in $_ifs
		do
			[ "$(cat /sys/class/net/"$_i"/address 2>/dev/null)" = "$_mac" ] && _pref=$_i
		done
	fi
	[ -n "$_pref" ] && _ifs="$_pref $(echo "$_ifs" | tr ' ' '\n' | grep -vx "$_pref")"
	if [ -n "$_mac" ] && [ -z "$_pref" ]
	then
		# e.g. ASUS X870E boards: the firmware PXE-boots from the Realtek RTL8127 (10 GbE), which
		# kernels before ~6.16 have no driver for; only the other port shows up, without a cable.
		_say "one-os: !! The port this PC network-booted from ($_mac) has no Linux driver in kernel $(uname -r)."
		_say "one-os: !! Linux only sees:$(for _i in $_ifs; do printf ' %s (%s)' "$_i" "$(cat /sys/class/net/"$_i"/address 2>/dev/null)"; done)"
		_say "one-os: !! Move the network cable to another LAN port and network-boot from that one."
	fi

	for _i in $_ifs
	do
		ip link set "$_i" up 2>/dev/null
	done

	_t=0 _found=""
	while [ $_t -le "$_wait" ]
	do
		for _i in $_ifs
		do
			if [ "$(cat /sys/class/net/"$_i"/carrier 2>/dev/null)" = 1 ]
			then
				_found=$_i
				break
			fi
		done
		[ -n "$_found" ] && break
		# Waiting on the PXE card alone for a while beats grabbing a card with no cable.
		[ $((_t % 5)) -eq 0 ] && _say "one-os: waiting for a link on${_ifs} ... ${_t}s"
		sleep 1; _t=$((_t + 1))
	done

	if [ -n "$_found" ]
	then
		_say "one-os: link up on $_found after ${_t}s ($(cat /sys/class/net/"$_found"/speed 2>/dev/null) Mb/s)"
		echo "DEVICE=$_found" >> /conf/param.conf
		# A fresh link can drop once more while it settles (EEE/autoneg); give DHCP a calm start.
		sleep 2
		return 0
	fi

	_say "one-os: no link after ${_wait}s. Card, driver, state:"
	for _i in $_ifs
	do
		_drv=$(basename "$(readlink /sys/class/net/"$_i"/device/driver 2>/dev/null)" 2>/dev/null)
		echo "  $_i $(cat /sys/class/net/"$_i"/address 2>/dev/null) driver=${_drv:-?} operstate=$(cat /sys/class/net/"$_i"/operstate 2>/dev/null)"
	done
	dmesg | grep -iE 'link|firmware|r8169|r8125|igc|e1000e' | tail -12
	_say "one-os: check the cable/switch port, or boot with oneos.linkwait=180."
	# Let live-boot try anyway: ipconfig waits ethdevice-timeout= seconds more on each.
	echo "DEVICE='${_ifs# }'" >> /conf/param.conf
	return 0
}

#!/bin/sh
# oneos-netboot.sh — live-config hook for a network-booted home base.
#
# The iPXE menu boots the home base with live-config.hooks=<server>/hooks/oneos-netboot.sh;
# live-config downloads this file and runs it as root early in boot (live-config(7)).
# A network-booted home base has no persistence, so without this nothing survives a reset.
#  3. SSH for the operator (oneos-ssh.sh): their public keys only, passwords refused.
#  0. /usr/local/bin/oneos-* are replaced by the server's current copies (<server>/tools/).
#  1. The display never blanks or powers off (X's default is 10 min; some TVs don't wake up).
#  2. oneos-netstatus posts a status snapshot (desktop, display, disks, GPU, errors, the
#     SteamOS installer's log) to <server>/client-status every 30 s, so the operator can see
#     what the PC is doing from the server: build/netboot/clients/<mac>/status.txt.

srv=$(sed -n 's/.*oneos\.server=\([^ ]*\).*/\1/p' /proc/cmdline)
[ -n "$srv" ] || exit 0

# 0. The server's copy of the one-os tools wins: fixes reach network-booted PCs without an ISO rebuild.
for t in $(wget -q -T 10 -O - "$srv/tools/" 2>/dev/null); do
  case "$t" in oneos-*) ;; *) continue ;; esac
  wget -q -T 30 -O "/usr/local/bin/$t.new" "$srv/tools/$t" && [ -s "/usr/local/bin/$t.new" ] &&
    chmod 0755 "/usr/local/bin/$t.new" && mv -f "/usr/local/bin/$t.new" "/usr/local/bin/$t"
  rm -f "/usr/local/bin/$t.new"
done

mkdir -p /etc/X11/xorg.conf.d
cat >/etc/X11/xorg.conf.d/10-oneos-noblank.conf <<'EOF'
# one-os (network boot): keep the screen on, an install takes longer than X's 10 min default
Section "ServerFlags"
    Option "BlankTime"   "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime"     "0"
EndSection
EOF

cat >/usr/local/sbin/oneos-netstatus <<'EOF'
#!/bin/bash
# Posts this PC's status to the one-os network boot server every 30 s (see oneos-netboot.sh).
srv=$(sed -n 's/.*oneos\.server=\([^ ]*\).*/\1/p' /proc/cmdline)
mac=$(sed -n 's/.*oneos\.mac=\([^ ]*\).*/\1/p' /proc/cmdline)
[[ -n $mac ]] || mac=$(cat /sys/class/net/*/address 2>/dev/null | grep -v '^00:00' | head -1 | tr : -)
X="env DISPLAY=:0 XAUTHORITY=/var/run/lightdm/root/:0"
out=/run/oneos-netstatus.txt
while :; do
  {
    monitor=$($X xset q 2>/dev/null | sed -n 's/^ *Monitor is \(.*\)/\1/p')
    outputs=$($X xrandr --current 2>/dev/null | awk '/ connected/{printf "%s%s", s, $1; s=","}')
    task=""
    pgrep -f '/usr/local/bin/oneos-steamos' >/dev/null && task=" installer=running"
    [[ -f /var/log/oneos-steamos.log ]] && task+=" installer-log=$(grep -c . /var/log/oneos-steamos.log)lines"
    echo "up=$(cut -d. -f1 /proc/uptime)s system=$(systemctl is-system-running 2>/dev/null)" \
         "lightdm=$(systemctl is-active lightdm 2>/dev/null) xorg=$(pgrep -x Xorg >/dev/null && echo yes || echo no)" \
         "monitor=${monitor:-?} outputs=${outputs:-none} sessions=$(loginctl list-sessions --no-legend 2>/dev/null | grep -c .)$task"
    echo
    echo "== cmdline";      cat /proc/cmdline
    echo "== failed units"; systemctl --failed --no-legend --plain 2>&1
    echo "== display";      $X xrandr --current 2>&1 | grep -E ' connected|\*'; $X xset q 2>&1 | grep -A2 -E 'DPMS|Screen Saver'
    echo "== gpu";          lspci -nnk 2>/dev/null | grep -A3 -E 'VGA|3D controller'
    echo "== disks";        lsblk -o NAME,SIZE,TYPE,PARTLABEL,FSTYPE,MODEL 2>&1
    echo "== memory";       free -m
    echo "== SteamOS installer log (last 40 lines)"; tail -40 /var/log/oneos-steamos.log 2>/dev/null
    echo "== kernel: gpu, drm, nvme, errors"; dmesg 2>/dev/null | grep -iE 'nouveau|amdgpu|drm|nvme|error|fail|firmware' | tail -40
    echo "== Xorg errors";  grep -E '\(EE\)' /var/log/Xorg.0.log 2>/dev/null | tail -20
    echo "== lightdm";      journalctl -b -u lightdm --no-pager -q 2>&1 | tail -15
    echo "== journal errors"; journalctl -b -p err --no-pager -q 2>&1 | tail -40
  } >"$out.new" 2>&1
  mv -f "$out.new" "$out"
  curl -s -m 15 --data-binary @"$out" -H 'Content-Type: text/plain' "$srv/client-status?mac=$mac" >/dev/null
  sleep 30
done
EOF
chmod 0755 /usr/local/sbin/oneos-netstatus

# A transient unit: its own cgroup, so it outlives live-config's service.
systemd-run --no-block --unit=oneos-netstatus --description="one-os status to $srv" \
  --property=Restart=always --property=RestartSec=10 /usr/local/sbin/oneos-netstatus >/dev/null 2>&1 ||
  (setsid /usr/local/sbin/oneos-netstatus >/dev/null 2>&1 &)
# 3. SSH with the operator's key, if the server offers one (oneos-ssh.sh; keys only). In the
#    background: installing openssh-server must not hold up the desktop.
systemd-run --no-block --unit=oneos-ssh --description="one-os SSH (keys only)" \
  sh -c "wget -q -T 20 -O - '$srv/hooks/oneos-ssh.sh' | sh" >/dev/null 2>&1 ||
  (setsid sh -c "wget -q -T 20 -O - '$srv/hooks/oneos-ssh.sh' | sh" >/dev/null 2>&1 &)
echo "oneos-netboot hook: screen blanking off, status → $srv" >/dev/ttyS0 2>/dev/null
exit 0

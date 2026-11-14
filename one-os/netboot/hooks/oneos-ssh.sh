#!/bin/sh
# oneos-ssh.sh — SSH into a network-booted home base with the operator's key (keys only).
#
# Run by oneos-netboot.sh at boot, or by hand on a running PC:
#   curl -s http://<server>:8780/hooks/oneos-ssh.sh | sudo sh
# Gets <server>/ssh/authorized_keys (public keys the operator chose: scripts/pxe.sh ssh-key),
# installs openssh-server if the image lacks it, and refuses passwords: the live user's
# password is public ("live"). Without authorized_keys on the server it does nothing.
# Then, from the server: ssh user@<pc>   (user has passwordless sudo on the home base)

srv=$(sed -n 's/.*oneos\.server=\([^ ]*\).*/\1/p' /proc/cmdline)
srv=${srv:-${1:-}}
[ -n "$srv" ] || { echo "oneos-ssh: no oneos.server= on the kernel command line; pass the server URL" >&2; exit 0; }

keys=$(wget -q -T 10 -O - "$srv/ssh/authorized_keys" 2>/dev/null)
case "$keys" in
  ssh-*|ecdsa-*|sk-*) ;;
  *) echo "oneos-ssh: the server offers no SSH keys (scripts/pxe.sh ssh-key) — SSH stays off"; exit 0 ;;
esac

# Keys only, before sshd ever starts.
mkdir -p /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/10-oneos.conf <<'EOF'
# one-os network boot: the operator's keys only (the live password is public)
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers user
EOF

home=/home/user
mkdir -p "$home/.ssh"
printf '%s\n' "$keys" >"$home/.ssh/authorized_keys"
chmod 700 "$home/.ssh"; chmod 600 "$home/.ssh/authorized_keys"
chown -R 1000:1000 "$home/.ssh" 2>/dev/null || true

if ! command -v sshd >/dev/null 2>&1 && [ ! -x /usr/sbin/sshd ]; then
  echo "oneos-ssh: installing openssh-server…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null 2>&1
  apt-get install -y -qq --no-install-recommends openssh-server >/dev/null 2>&1 ||
    { echo "oneos-ssh: could not install openssh-server (no internet?)" >&2; exit 0; }
fi
systemctl enable --now ssh >/dev/null 2>&1 || systemctl restart ssh >/dev/null 2>&1 || /usr/sbin/sshd

ip=$(hostname -I 2>/dev/null | cut -d' ' -f1)
mac=$(sed -n 's/.*oneos\.mac=\([^ ]*\).*/\1/p' /proc/cmdline)
wget -q -T 10 -O /dev/null "$srv/report?stage=ssh&msg=ssh+user@$ip+ready+(keys+only)&mac=$mac" 2>/dev/null
echo "oneos-ssh: ready — ssh user@$ip"
exit 0

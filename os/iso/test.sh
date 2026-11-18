#!/usr/bin/env bash
# os/iso/test.sh — install the bashOS ISO into a VM with nobody at the keyboard, and check the result
# the way its person would: the unattended install from a cidata seed (os/iso/seed.sh), the first
# boot from the disk, ssh with the seed's key, bashos-firstboot finishing online, and `bashos os
# status`. Needs QEMU with KVM (the os-iso workflow, or any Linux x86_64 host); TCG works but
# takes hours. Evidence lands in build/iso/test/: the serial log, a screenshot every few minutes,
# the first-boot log, the status.
set -Eeuo pipefail

OS_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib.sh
source "$OS_SRC/os/lib.sh"

GIB=$((1024 * 1024 * 1024))
DISK_GB=40
USER_NAME=bashos
HOST_NAME=bashos-ci
PORT=${BASHOS_ISO_TEST_PORT:-2222}

usage() {
  cat <<'EOF'
usage: bashos os iso test [ISO] [options]

  ISO              default: the newest build/iso/bashos-*.iso
  --timeout MIN    how long the install and the first boot may take together (default 90)
  --out DIR        the evidence (default: build/iso/test)
  --keep           leave the VM running at the end (ssh -p 2222 bashos@127.0.0.1 with DIR/id_ed25519)
  -h, --help
EOF
}

# The UEFI firmware and a writable copy of its variables (Ubuntu's, Arch's or QEMU's own names).
firmware() {
  local code vars c v
  for c in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/edk2/x64/OVMF_CODE.4m.fd /usr/share/OVMF/OVMF_CODE.fd \
    "$(dirname "$(command -v qemu-system-x86_64)")/../share/qemu/edk2-x86_64-code.fd"; do
    [[ -r $c ]] && { code=$c; break; }
  done
  for v in /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/edk2/x64/OVMF_VARS.4m.fd /usr/share/OVMF/OVMF_VARS.fd \
    "$(dirname "$(command -v qemu-system-x86_64)")/../share/qemu/edk2-i386-vars.fd"; do
    [[ -r $v ]] && { vars=$v; break; }
  done
  [[ -n ${code:-} && -n ${vars:-} ]] || os_die "no OVMF firmware (Ubuntu: apt install ovmf)"
  cp "$vars" "$OUT/vars.fd"
  printf '%s' "$code"
}

# qmp COMMAND [FILE] — one QMP command on the VM's socket (screendump takes a PNG path).
qmp() {
  python3 - "$SOCK" "$@" <<'PY'
import json, socket, sys
s = socket.socket(socket.AF_UNIX)
s.connect(sys.argv[1])
f = s.makefile("rw")
f.readline()
def cmd(name, **args):
    f.write(json.dumps({"execute": name, **({"arguments": args} if args else {})}) + "\n")
    f.flush()
    while True:
        reply = json.loads(f.readline())
        if "return" in reply or "error" in reply:
            return reply
cmd("qmp_capabilities")
if sys.argv[2] == "screendump":
    print(cmd("screendump", filename=sys.argv[3], format="png"))
else:
    print(cmd(sys.argv[2]))
PY
}

vm_ssh() {
  ssh -i "$OUT/id_ed25519" -p "$PORT" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=5 "$USER_NAME@127.0.0.1" "$@"
}

vm_alive() { [[ -f $OUT/qemu.pid ]] && kill -0 "$(cat "$OUT/qemu.pid")" 2>/dev/null; }

# On every exit: the VM stops (unless --keep) and its socket directory goes.
KEEP=0
cleanup() {
  ((KEEP)) && return 0
  stop_vm
  [[ -n ${SOCK:-} ]] && rm -rf "$(dirname "$SOCK")"
}

stop_vm() {
  vm_alive || return 0
  qmp system_powerdown >/dev/null 2>&1 || true
  for _ in $(seq 30); do vm_alive || return 0; sleep 1; done
  qmp quit >/dev/null 2>&1 || kill "$(cat "$OUT/qemu.pid")" 2>/dev/null || true
}

main() {
  local iso="" timeout=90 accel=kvm cpu=host code deadline shot=0 state=""
  OUT=$OS_SRC/build/iso/test
  while (($#)); do
    case $1 in
      --timeout) timeout=${2:?--timeout needs minutes}; shift ;;
      --out) OUT=${2:?--out needs a directory}; shift ;;
      --keep) KEEP=1 ;;
      -h | --help) usage; return 0 ;;
      -*) usage >&2; return 2 ;;
      *) iso=$1 ;;
    esac
    shift
  done
  if [[ -z $iso ]]; then
    iso=$(find "$OS_SRC/build/iso" -maxdepth 1 -name 'bashos-*.iso' -print 2>/dev/null | sort | tail -1)
  fi
  [[ -n $iso && -f $iso ]] || os_die "no ISO: build one with bashos os iso build, or name it"
  os_has qemu-system-x86_64 || os_die "no qemu-system-x86_64"
  if [[ ! -w /dev/kvm ]]; then
    accel=tcg cpu=max
    os_warn "no usable /dev/kvm: emulating, which takes hours"
  fi

  rm -rf "$OUT"
  mkdir -p "$OUT/screens"
  OUT=$(cd "$OUT" && pwd)
  # A unix socket's path must stay under 104 bytes, which a deep build directory can pass.
  SOCK="$(mktemp -d /tmp/bashos-iso.XXXXXX)/qmp.sock"
  trap cleanup EXIT
  printf '%sbashOS%s ISO install test · %s · %s\n' "$_os_b" "$_os_0" "$(basename "$iso")" "$accel"

  os_step "seed"
  ssh-keygen -q -t ed25519 -N '' -C bashos-iso-test -f "$OUT/id_ed25519"
  "$OS_DIR/iso/seed.sh" --user "$USER_NAME" --hostname "$HOST_NAME" --disk /dev/vda \
    --disk-bytes $((DISK_GB * GIB)) --keys "$OUT/id_ed25519.pub" \
    --password-hash "$(openssl passwd -6 "$(head -c 18 /dev/urandom | base64)")" --out "$OUT/cidata"
  [[ -f $OUT/cidata.iso ]] || os_die "the seed was not packed as an ISO (install xorriso)"

  os_step "install"
  qemu-img create -q -f qcow2 "$OUT/disk.qcow2" "${DISK_GB}G"
  code=$(firmware)
  # The empty disk boots first and falls through to the ISO; once installed, it boots itself.
  # The seed is a second CD-ROM, so the target stays /dev/vda.
  qemu-system-x86_64 -machine q35 -accel "$accel" -cpu "$cpu" -smp 4 -m 8G \
    -drive "if=pflash,format=raw,readonly=on,file=$code" -drive "if=pflash,format=raw,file=$OUT/vars.fd" \
    -drive "file=$OUT/disk.qcow2,format=qcow2,if=none,id=disk" -device virtio-blk-pci,drive=disk,bootindex=0 \
    -drive "file=$iso,media=cdrom,if=none,id=iso,readonly=on" -device ide-cd,drive=iso,bus=ide.0,bootindex=1 \
    -drive "file=$OUT/cidata.iso,media=cdrom,if=none,id=seed,readonly=on" -device ide-cd,drive=seed,bus=ide.1 \
    -netdev "user,id=net,hostfwd=tcp:127.0.0.1:$PORT-:22" -device virtio-net-pci,netdev=net \
    -device virtio-vga -display none -device virtio-rng-pci \
    -serial "file:$OUT/serial.log" -qmp "unix:$SOCK,server,nowait" \
    -pidfile "$OUT/qemu.pid" -daemonize || os_die "QEMU did not start (its message is above)"
  deadline=$(($(date +%s) + timeout * 60))

  # The live system has no such user, so ssh as them answers only from the installed disk.
  until vm_ssh true </dev/null 2>/dev/null; do
    vm_alive || os_die "QEMU exited during the install (serial: $OUT/serial.log)"
    (($(date +%s) < deadline)) || { qmp screendump "$OUT/screens/timeout.png" >/dev/null || true; os_die "no ssh from the installed system within $timeout min (see $OUT/screens)"; }
    if ((SECONDS / 180 >= shot)); then
      qmp screendump "$OUT/screens/$(printf '%03d' "$shot").png" >/dev/null 2>&1 || true
      shot=$((shot + 1))
    fi
    sleep 15
  done
  os_ok "installed: ssh $USER_NAME@$HOST_NAME answers with the seed's key"

  os_step "first boot"
  until state=$(vm_ssh 'if [ -e /var/lib/bashos/provisioned ]; then echo done; elif [ -e /var/lib/bashos/firstboot-failed ]; then echo failed; else echo waiting; fi' </dev/null 2>/dev/null) &&
    [[ $state == "done" || $state == "failed" ]]; do
    (($(date +%s) < deadline)) || { state=timeout; break; }
    sleep 20
  done
  vm_ssh 'cat /var/log/bashos-firstboot.log' >"$OUT/firstboot.log" 2>&1 </dev/null || true
  vm_ssh 'journalctl -b --no-pager -u bashos-firstboot' >"$OUT/firstboot.journal" 2>&1 </dev/null || true
  vm_ssh 'cat /etc/bashos/build-info; uname -r' >"$OUT/build-info" 2>&1 </dev/null || true
  vm_ssh 'NOTMUX=1 bashos os status' >"$OUT/status.txt" 2>&1 </dev/null || true
  qmp screendump "$OUT/screens/final.png" >/dev/null 2>&1 || true
  ((KEEP)) || stop_vm
  cat "$OUT/status.txt"

  [[ $state == "done" ]] || os_die "first boot $state (log: $OUT/firstboot.log)"
  local piece missing=()
  for piece in base layer runtime engine provision; do
    grep -q "^\[ OK \] $piece " "$OUT/status.txt" || missing+=("$piece")
  done
  if grep -q '^\[CRIT\]' "$OUT/status.txt" || ((${#missing[@]})); then
    os_die "bashos os status: ${missing[*]:-a CRIT verdict} not OK"
  fi
  os_ok "bashOS installed unattended and finished its first boot ($OUT)"
}

main "$@"

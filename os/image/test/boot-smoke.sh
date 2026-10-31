#!/usr/bin/env bash
# os/image/test/boot-smoke.sh — boot a built bashOS image the way forge would meet it, and check
# what its person would: the first boot provisions itself from a seed drive, ssh works with the
# seed's key, the root filesystem grew into the disk, `bashos-os status` holds, the kernel routes
# a command (dry run, no credential needed), and with --harness the Harness Console answers.
#
#   bashos os image test [--image FILE] [--arch x86-64|arm64] [--disk SIZE] [--memory MB] [--timeout SECS]
#                        [--harness [--harness-wait SECS]] [--keep] [--docker]
#
# Needs qemu-system-<arch>, UEFI firmware (Debian: ovmf | qemu-efi-aarch64), qemu-utils, mtools,
# openssh-client — or --docker, which runs it inside debian:trixie with those. KVM is used
# when /dev/kvm is writable; otherwise TCG (slow: give it --timeout 2400).
# Evidence (serial log, status, checks) lands in $OUT (default os/image/mkosi.output/smoke).
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_DIR="$(cd "$HERE/.." && pwd)"
OS_SRC="$(cd "$IMAGE_DIR/../.." && pwd)"
# shellcheck source=../../lib.sh
source "$OS_SRC/os/lib.sh"

case $(uname -m) in
  x86_64 | amd64) arch=x86-64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) arch=$(uname -m) ;;
esac
image="" disk=16G memory=3072 timeout=1200 harness=0 harness_wait=1200 keep=0 docker=0
OUT=${OUT:-$IMAGE_DIR/mkosi.output/smoke}
while (($#)); do
  case $1 in
    --image) image=${2:?}; shift ;;
    --arch) arch=${2:?}; shift ;;
    --disk) disk=${2:?}; shift ;;
    --memory) memory=${2:?}; shift ;;
    --timeout) timeout=${2:?}; shift ;;
    --harness) harness=1 ;;
    --harness-wait) harness_wait=${2:?}; shift ;;
    --keep) keep=1 ;;
    --docker) docker=1 ;;
    -h | --help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) os_die "unknown option $1" ;;
  esac
  shift
done
[[ -n $image ]] || image=$(find "$IMAGE_DIR/mkosi.output" -maxdepth 1 -name 'bashos*.raw' -print 2>/dev/null | sort | tail -1)
[[ -f $image ]] || os_die "no image (bashos os image build first, or --image FILE)"

if ((docker)); then
  case $arch in x86-64) platform=linux/amd64 qemu=qemu-system-x86 fw=ovmf ;; arm64) platform=linux/arm64 qemu=qemu-system-arm fw=qemu-efi-aarch64 ;; esac
  kvm=()
  [[ -w /dev/kvm ]] && kvm=(--device /dev/kvm)
  mkdir -p "$OUT"
  img_dir=$(cd "$(dirname "$image")" && pwd)
  flags=(--arch "$arch" --disk "$disk" --memory "$memory" --timeout "$timeout")
  ((harness)) && flags+=(--harness --harness-wait "$harness_wait")
  ((keep)) && flags+=(--keep)
  exec docker run --rm --platform "$platform" "${kvm[@]}" \
    -v "$OS_SRC:/src:ro" -v "$img_dir:/img:ro" -v "$(cd "$OUT" && pwd):/out" -e OUT=/out \
    debian:trixie bash -c '
      set -Eeuo pipefail
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq --no-install-recommends "$0" "$1" qemu-utils mtools openssh-client curl >/dev/null
      /src/os/image/test/boot-smoke.sh --image "/img/$2" "${@:3}"
    ' "$qemu" "$fw" "$(basename "$image")" "${flags[@]}"
fi

for tool in qemu-img mformat mcopy ssh ssh-keygen; do os_has "$tool" || os_die "missing $tool"; done
mkdir -p "$OUT"
work=$(mktemp -d)
qemu_pid=""
cleanup() {
  [[ -n $qemu_pid ]] && kill "$qemu_pid" 2>/dev/null || true
  if ((keep)); then echo "kept: $work"; else rm -rf "$work"; fi
}
trap cleanup EXIT

# The seed drive: a user, this run's ssh key, and the harness on loopback.
ssh-keygen -q -t ed25519 -N '' -f "$work/key"
cp "$work/key.pub" "$work/authorized_keys"
cat >"$work/seed.env" <<'EOF'
BASHOS_USER=smoke
BASHOS_HOSTNAME=bashos-smoke
BASHOS_SHELL=zsh
BASHOS_SUDO_NOPASSWD=yes
BASHOS_HARNESS=native
EOF
mformat -C -f 1440 -v BASHOS-SEED -i "$work/seed.img" ::
mcopy -i "$work/seed.img" "$work/seed.env" "$work/authorized_keys" ::

# A copy-on-write disk bigger than the image, so first-boot growth is observable.
qemu-img create -q -f qcow2 -b "$(cd "$(dirname "$image")" && pwd)/$(basename "$image")" -F raw "$work/disk.qcow2" "$disk"

# TCG's translation cache defaults to 1 GB on top of the guest's RAM; 256 MB is plenty here.
accel=tcg,tb-size=256 cpu=max
[[ -w /dev/kvm ]] && accel=kvm cpu=host
port=$((20000 + RANDOM % 20000))
case $arch in
  x86-64)
    qemu=(qemu-system-x86_64 -machine q35 -accel "$accel" -bios /usr/share/ovmf/OVMF.fd)
    serial=ttyS0 ;;
  arm64)
    qemu=(qemu-system-aarch64 -machine virt -accel "$accel" -bios /usr/share/qemu-efi-aarch64/QEMU_EFI.fd)
    serial=ttyAMA0 ;;
  *) os_die "no QEMU recipe for $arch" ;;
esac
os_step "boot $(basename "$image") · $arch · ${accel%%,*} · ${memory} MB · disk $disk"
# systemd-stub appends SMBIOS type 11 'kernel-cmdline-extra' to the UKI's command line: the
# serial console exists only in this VM, never in the image.
"${qemu[@]}" -cpu "$cpu" -m "$memory" -smp 2 -display none -no-reboot \
  -drive "if=virtio,file=$work/disk.qcow2,format=qcow2" \
  -drive "if=virtio,file=$work/seed.img,format=raw,readonly=on" \
  -netdev "user,id=n0,hostfwd=tcp:127.0.0.1:$port-:22" -device virtio-net-pci,netdev=n0,romfile= \
  -smbios "type=11,value=io.systemd.stub.kernel-cmdline-extra=console=$serial" \
  -serial "file:$OUT/serial.log" &
qemu_pid=$!

deadline=$((SECONDS + timeout))
until grep -q 'bashos-provision: ready' "$OUT/serial.log" 2>/dev/null; do
  kill -0 "$qemu_pid" 2>/dev/null || { tail -40 "$OUT/serial.log" >&2; os_die "QEMU exited before provisioning finished"; }
  ((SECONDS < deadline)) || { tail -60 "$OUT/serial.log" >&2; os_die "no 'bashos-provision: ready' within ${timeout}s"; }
  sleep 5
done
os_ok "first boot provisioned ($((timeout - deadline + SECONDS))s)"

vm() {
  ssh -q -i "$work/key" -p "$port" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=10 -o BatchMode=yes smoke@127.0.0.1 "$@"
}
for _ in $(seq 1 30); do vm true 2>/dev/null && break; sleep 5; done
vm true || os_die "ssh with the seed's key failed"
os_ok "ssh smoke@ with the seed's key"

fail=0
diagnose() { # what the console and the harness were doing, from inside the VM
  vm 'journalctl -b --no-pager -u getty@tty1 | tail -30; echo; journalctl -b --no-pager _UID=$(id -u) | tail -80;
      echo; cat ~/.local/state/bashos/console.log 2>/dev/null; echo; loginctl list-sessions --no-legend;
      echo; systemctl --user --no-pager status bashos-harness.service | tail -20;
      journalctl --user --no-pager -u bashos-harness -n 80' >>"$OUT/diagnostics.txt" 2>&1 || true
}
check() { # check NAME CMD… — run CMD in the VM, keep its output as evidence
  local name=$1 rc=0
  shift
  vm "$@" >"$OUT/$name.txt" 2>&1 || rc=$?
  if ((rc == 0)); then os_ok "$name"; else os_warn "$name failed (exit $rc) — $OUT/$name.txt"; fail=1; fi
}
check system 'systemctl is-system-running --wait >/dev/null; systemctl --failed --no-legend; s=$(systemctl is-system-running); echo "$s"; [ "$s" = running ]'
check grown 'df -BG --output=size / | tail -1 | tr -dc 0-9 | { read -r g; echo "root ${g}G"; [ "$g" -ge 8 ]; }'
check layer 'bashos-os version && test -x /opt/bashos/.venv/bin/bashos && command -v opencode claude'
check route 'cd /tmp && bashos run -n "/sh list the five largest files here"'
check console 'tmux has-session -t =console && tmux list-windows -t =console -F "#{window_name}" | grep -qx bashos'
((fail)) && diagnose
if ((harness)); then
  # A first start installs the console's requirements and builds its page: slow under TCG.
  check harness "for i in \$(seq 1 $((harness_wait / 10))); do curl -fsS -o /dev/null http://127.0.0.1:4001/api/health && exit 0; sleep 10; done; exit 1"
fi
((fail)) && diagnose
# Evidence, not a gate: the engine boots from the root-owned layer (a live model call needs a
# credential the test does not have).
vm 'cd ~ && timeout 180 bashos opencode status' >"$OUT/engine.txt" 2>&1 || true
vm 'bashos-os status' >"$OUT/status.txt" 2>&1 || true
cat "$OUT/status.txt"
((fail == 0)) || os_die "smoke test failed — evidence in $OUT"
os_ok "smoke test passed — evidence in $OUT"

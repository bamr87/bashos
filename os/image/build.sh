#!/usr/bin/env bash
# os/image/build.sh — build the bootable bashOS disk image with mkosi: Debian 13, systemd-boot, a
# unified kernel image, and the bashOS layer applied (os/install.sh --image) at /opt/bashos.
#
#   bashos os image build [--arch x86-64|arm64] [--out DIR] [--seed DIR] [--docker] [-- MKOSI…]
#
#   --arch     target architecture (default: this machine's)
#   --out      output directory (default: os/image/mkosi.output)
#   --seed     bake a first-boot seed into the image (/etc/bashos/seed): seed.env, authorized_keys,
#              harness.env — the image file then holds them; prefer a BASHOS-SEED drive
#   --docker   run this script inside debian:trixie with --privileged (from macOS, or any host
#              without mkosi); the image lands in the same --out
#
# Needs Linux with mkosi >= 25, as root (or in a privileged container). The output is a GPT disk
# image (bashos_<version>.raw) to write to a USB stick or a disk: os/image/README.md.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_SRC="$(cd "$HERE/../.." && pwd)"
# shellcheck source=../lib.sh
source "$OS_SRC/os/lib.sh"
# shellcheck source=../install/packages.sh
source "$OS_DIR/install/packages.sh"

case $(uname -m) in
  x86_64 | amd64) arch=x86-64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) arch=$(uname -m) ;;
esac
out="$HERE/mkosi.output"
seed="" docker=0 mkosi_args=()
while (($#)); do
  case $1 in
    --arch) arch=${2:?--arch x86-64|arm64}; shift ;;
    --out) out=${2:?--out DIR}; shift ;;
    --seed) seed=${2:?--seed DIR}; shift ;;
    --docker) docker=1 ;;
    --) shift; mkosi_args=("$@"); break ;;
    -h | --help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) os_die "unknown option $1 (bashos os image build --help)" ;;
  esac
  shift
done

# What was built, from the host's git (a container cannot always read a submodule's .git).
commit=$(git -C "$OS_SRC" rev-parse HEAD 2>/dev/null || printf '%s' "${BASHOS_BUILD_COMMIT:-unknown}")
version=$(git -C "$OS_SRC" describe --tags --always --dirty 2>/dev/null || printf '%s' "${BASHOS_BUILD_VERSION:-$(date +%Y.%m.%d)}")
dirty=$([[ $version == *-dirty ]] && echo yes || echo "${BASHOS_BUILD_DIRTY:-no}")

if ((docker)); then
  os_has docker || os_die "--docker needs docker"
  case $arch in x86-64) platform=linux/amd64 ;; arm64) platform=linux/arm64 ;; *) os_die "--docker: no platform for $arch" ;; esac
  mkdir -p "$out"
  out_abs=$(cd "$out" && pwd)
  seed_mount=()
  if [[ -n $seed ]]; then
    seed_mount=(-v "$(cd "$seed" && pwd):/seed:ro")
    seed=/seed
  fi
  # A version-pinned base would go stale; trixie is the release the image is built from.
  exec docker run --rm --privileged --platform "$platform" \
    -v "$OS_SRC:/src:ro" -v "$out_abs:/out" "${seed_mount[@]}" \
    -e BASHOS_BUILD_COMMIT="$commit" -e BASHOS_BUILD_VERSION="${version%-dirty}" -e BASHOS_BUILD_DIRTY="$dirty" \
    -e BASHOS_BUILD_SOURCE="$OS_SRC" \
    debian:trixie bash -c '
      set -Eeuo pipefail
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq --no-install-recommends mkosi git rsync ca-certificates >/dev/null
      /src/os/image/build.sh --arch "$0" --out /out ${1:+--seed "$1"} -- "${@:2}"
    ' "$arch" "$seed" "${mkosi_args[@]}"
fi

[[ $(uname -s) == Linux ]] || os_die "mkosi builds on Linux — from here use: bashos os image build --docker"
os_has mkosi || os_die "mkosi not found (Debian 13: sudo apt install mkosi), or use --docker"

mkdir -p "$out"
stage="$out/stage"
rm -rf "$stage"
mkdir -p "$stage/opt/bashos" "$stage/etc/bashos"

# The layer, exactly what git would ship (os/install/runtime.sh copies the same way).
if git -C "$OS_SRC" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$OS_SRC" ls-files -z -co --exclude-standard | tar -C "$OS_SRC" --null -T - -cf - | tar -C "$stage/opt/bashos" -xf -
else
  rsync -a --filter=':- .gitignore' --exclude=.git --exclude=.venv --exclude=/os/image/mkosi.output \
    "$OS_SRC/" "$stage/opt/bashos/"
fi
cat >"$stage/etc/bashos/build-info" <<EOF
commit=$commit
dirty=$dirty
source=${BASHOS_BUILD_SOURCE:-$OS_SRC}
layer=/opt/bashos
version=$version
built=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
if [[ -n $seed ]]; then
  os_warn "baking the seed in $seed into the image: the image file now carries it"
  install -d -m 0700 "$stage/etc/bashos/seed"
  cp -a "$seed"/. "$stage/etc/bashos/seed/"
  chmod -R go-rwx "$stage/etc/bashos/seed"
fi

mapfile -t packages < <(os_packages --all base console services)
os_step "mkosi build · $arch · $version · ${#packages[@]} layer packages"
mkosi --directory "$HERE" --output-directory "$out" --architecture "$arch" \
  --image-version "${version//[^A-Za-z0-9._-]/_}" --extra-tree "$stage:/" \
  --package "$(IFS=,; printf '%s' "${packages[*]}")" "${mkosi_args[@]}" --force build
rm -rf "$stage"
os_ok "$(find "$out" -maxdepth 1 -name 'bashos*.raw' -newer "$out" -print -quit 2>/dev/null || find "$out" -maxdepth 1 -name 'bashos*.raw' | head -1)"

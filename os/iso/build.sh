#!/usr/bin/env bash
# os/iso/build.sh — the bashOS ISO: Amrchy (amrchy/, the framework) with the bashOS layer
# (os/amrchy/layer), built by Omarchy's own ISO builder at the commits os/iso/iso.conf pins.
#
#   1. fetch    omarchy-iso and omarchy-pkgs at their pins, into build/iso/src/
#   2. stage    a copy of amrchy/ with install/layers/bashos/ (the layer, the bashOS tree as its
#               payload, a build stamp), into build/iso/stage/amrchy
#   3. build    omarchy-iso-make --local-source on the staged tree (Docker, privileged; on an
#               ARM host the x86_64 builder runs emulated), into build/iso/bashos-*.iso
#
# The ISO installs like Omarchy's: the configurator, or unattended from a `cidata` drive
# (os/iso/seed.sh). The layer puts bashOS at /opt/bashos during the install and its first
# boot, once online, finishes the runtime (docs/OS.md).
set -Eeuo pipefail

OS_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib.sh
source "$OS_SRC/os/lib.sh"

ISO_DIR="$OS_DIR/iso"
BUILD=${BASHOS_ISO_BUILD:-$OS_SRC/build/iso}

usage() {
  cat <<'EOF'
usage: bashos os iso build [options]

  --stage-only   fetch nothing, build nothing: only stage the Amrchy tree with the layer
  --no-fetch     use the builders already in build/iso/src (no network)
  --out DIR      where the ISO and its checksum go (default: build/iso)
  --print-pins   the pinned builder commits, then exit
  -h, --help
EOF
}

# iso_conf KEY — one value from iso.conf (data, never sourced).
iso_conf() {
  sed -n "s/^$1=//p" "$ISO_DIR/iso.conf" | sed 's/[[:space:]]*#.*$//' | head -1
}

# The bamr87/amrchy commit amrchy/ holds ("unknown" in a shallow clone, which lacks the squash
# commit that records it), and the bashOS commit the build is made from.
amrchy_split() {
  local split
  split=$(git -C "$OS_SRC" log -1 --grep='^git-subtree-dir: amrchy$' --format=%B 2>/dev/null |
    sed -n 's/^git-subtree-split: //p')
  printf '%s' "${split:-unknown}"
}
bashos_commit() { git -C "$OS_SRC" rev-parse HEAD 2>/dev/null || printf 'unknown'; }
bashos_dirty() { [[ -n $(git -C "$OS_SRC" status --porcelain 2>/dev/null) ]] && printf yes || printf no; }

# iso_fetch NAME REPO COMMIT — a checkout of exactly COMMIT at build/iso/src/NAME.
iso_fetch() {
  local name=$1 repo=$2 commit=$3 dir="$BUILD/src/$1"
  if [[ $(git -C "$dir" rev-parse HEAD 2>/dev/null) == "$commit" ]]; then
    os_log "${_os_d}unchanged${_os_0} $name at ${commit:0:12}"
    return 0
  fi
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" remote remove origin 2>/dev/null || true
  git -C "$dir" remote add origin "$repo"
  git -C "$dir" fetch -q --depth 1 origin "$commit"
  git -C "$dir" checkout -q --detach FETCH_HEAD
  [[ -f $dir/.gitmodules ]] && git -C "$dir" submodule update -q --init --recursive --depth 1
  os_ok "$name at ${commit:0:12}"
}

# tree_copy DEST PATHSPEC… — the tracked files under the given pathspecs, as they are in the
# working tree (an uncommitted change is built, and the stamp says dirty=yes).
tree_copy() {
  local dest=$1
  shift
  mkdir -p "$dest"
  git -C "$OS_SRC" ls-files -z -c -- "$@" | tar -C "$OS_SRC" --null -T - -cf - | tar -C "$dest" -xf -
}

iso_stage() {
  local stage="$BUILD/stage/amrchy" layer tmp
  os_step "stage"
  rm -rf "$BUILD/stage"
  tmp="$BUILD/stage/tmp"
  tree_copy "$tmp" amrchy
  mv "$tmp/amrchy" "$stage"
  rm -rf "$tmp"
  [[ -f $stage/install/post-install/layers.sh ]] || os_die "amrchy/ has no layers runner (amrchy/docs/layers.md)"
  os_ok "amrchy/ -> ${stage#"$OS_SRC"/} ($(find "$stage" -type f | wc -l | tr -d ' ') files)"

  layer="$stage/install/layers/bashos"
  mkdir -p "$layer"
  cp "$OS_DIR"/amrchy/layer/* "$layer/"
  # The bashOS tree the machine runs: everything but the framework itself (installed as
  # packages), the machine-lifecycle tool, the macOS terminal kit and the Debian image.
  tree_copy "$layer/payload" . ':!amrchy' ':!one-os' ':!chui' ':!os/image' ':!docs/media'
  cat >"$layer/build-info" <<EOF
commit=$(bashos_commit)
dirty=$(bashos_dirty)
source=bashos-iso
layer=/opt/bashos
amrchy=$(amrchy_split)
omarchy_iso=$(iso_conf OMARCHY_ISO_COMMIT)
omarchy_pkgs=$(iso_conf OMARCHY_PKGS_COMMIT)
built=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
  os_ok "layer bashos: $(du -sh "$layer/payload" | cut -f1) of bashOS at $(bashos_commit | cut -c1-12)"
}

iso_make() {
  local out=$1 builder="$BUILD/src/omarchy-iso" iso name platform=()
  os_step "build"
  os_has docker || os_die "the ISO builds in Docker: install it, or build on Linux with Docker"
  # The x86_64 builder image has no ARM variant: an ARM host (Apple Silicon) runs it emulated.
  case $(uname -m) in
    x86_64 | amd64) ;;
    *) platform=(env DOCKER_DEFAULT_PLATFORM=linux/amd64) ;;
  esac
  rm -f "$builder"/release/*.iso
  (cd "$builder" && "${platform[@]}" ./bin/omarchy-iso-make --no-boot-offer --keep-pkg-cache \
    --local-source "$BUILD/stage/amrchy" "$BUILD/src/omarchy-pkgs")
  iso=$(find "$builder/release" -maxdepth 1 -name '*.iso' -print | head -1)
  [[ -n $iso ]] || os_die "the builder made no ISO (its output is above)"
  name="bashos-$(date -u +%Y.%m.%d)-$(bashos_commit | cut -c1-7)-$(iso_conf BASHOS_ISO_ARCH).iso"
  mkdir -p "$out"
  mv "$iso" "$out/$name"
  cp "$BUILD/stage/amrchy/install/layers/bashos/build-info" "$out/$name.build-info"
  (cd "$out" && shasum -a 256 "$name" >"$name.sha256")
  os_ok "$out/$name ($(du -h "$out/$name" | cut -f1))"
}

main() {
  local stage_only=0 fetch=1 out=$BUILD
  while (($#)); do
    case $1 in
      --stage-only) stage_only=1 ;;
      --no-fetch) fetch=0 ;;
      --out) out=${2:?--out needs a directory}; shift ;;
      --print-pins)
        printf 'omarchy-iso  %s\nomarchy-pkgs %s\namrchy       %s\n' "$(iso_conf OMARCHY_ISO_COMMIT)" \
          "$(iso_conf OMARCHY_PKGS_COMMIT)" "$(amrchy_split)"
        return 0
        ;;
      -h | --help) usage; return 0 ;;
      *) usage >&2; return 2 ;;
    esac
    shift
  done
  printf '%sbashOS%s ISO · amrchy %s · build %s\n' "$_os_b" "$_os_0" "$(amrchy_split | cut -c1-12)" "${BUILD#"$OS_SRC"/}"
  if ((!stage_only && fetch)); then
    os_step "fetch"
    iso_fetch omarchy-iso "$(iso_conf OMARCHY_ISO_REPO)" "$(iso_conf OMARCHY_ISO_COMMIT)"
    iso_fetch omarchy-pkgs "$(iso_conf OMARCHY_PKGS_REPO)" "$(iso_conf OMARCHY_PKGS_COMMIT)"
  fi
  iso_stage
  ((stage_only)) && return 0
  iso_make "$out"
}

main "$@"

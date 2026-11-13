# os/install/engine.sh — OpenCode, the engine every bashOS command runs on, as a dependency bashOS
# owns. A bashOS machine runs npm's `latest` OpenCode, fetched as OpenCode's own platform binary
# straight from the registry (no Node needed) and checked against the registry's sha512. The
# copy is root-owned, so nothing running as the user can swap the binary that enforces the
# policy. A release is promoted only after `bashos opencode verify` proves it still enforces
# opencode/policy.py; one that fails keeps the machine on the newest release that passes.
# Sourced by the runtime phase and by `bashos os engine`; bashos-engine-update.timer runs
# `bashos os engine update` daily.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh

OS_ENGINE_REGISTRY=${BASHOS_ENGINE_REGISTRY:-https://registry.npmjs.org}
OS_ENGINE_HOME=/usr/local/lib/bashos/opencode # <version>/bin/opencode for each kept release
OS_ENGINE_BIN=$OS_ENGINE_HOME/current/bin/opencode
OS_ENGINE_RECORD=/etc/bashos/opencode       # read by opencode/server.py before PATH
OS_ENGINE_STATE=/var/lib/bashos/opencode.state

# The registry package with OpenCode's binary for this machine, chosen the way OpenCode's own
# postinstall does, with one deliberate difference: x64 always takes the baseline build. A
# bashOS disk boots wherever it is plugged in, and forge's i7-3820 has no AVX2.
os_engine_package() {
  local arch libc=""
  case $(uname -m) in
    x86_64 | amd64) arch=x64 ;;
    aarch64 | arm64) arch=arm64 ;;
    *) return 1 ;;
  esac
  if [[ -e /etc/alpine-release ]] || ldd --version 2>&1 | grep -qi musl; then libc=-musl; fi
  if [[ $arch == x64 ]]; then
    printf 'opencode-linux-x64-baseline%s\n' "$libc"
  else
    printf 'opencode-linux-%s%s\n' "$arch" "$libc"
  fi
}

# The version npm's `latest` tag names for opencode-ai, the package OpenCode publishes.
os_engine_latest() {
  curl -fsSL --max-time 30 "$OS_ENGINE_REGISTRY/opencode-ai/latest" | jq -re '.version'
}

# The newest stable release of one major: the fallback when `latest` is a major the contract
# rejects (OpenCode 2 today, bamr87/bashos#71).
os_engine_newest_in() {
  curl -fsSL --max-time 120 -H 'Accept: application/vnd.npm.install-v1+json' "$OS_ENGINE_REGISTRY/opencode-ai" |
    jq -r --arg m "$1" '.versions | keys[] | select(test("^" + $m + "\\.[0-9]+\\.[0-9]+$"))' | sort -V | tail -1
}

# The managed engine's version, or nothing.
os_engine_current() {
  local bin
  bin=$(os_path "$OS_ENGINE_BIN")
  [[ -x $bin ]] || return 0
  "$bin" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# os_engine_fetch VERSION DIR — DIR/bin/opencode, from the registry, sha512 checked. No root.
os_engine_fetch() {
  local version=$1 dest=$2 pkg meta url want got tmp
  pkg=$(os_engine_package) || { os_warn "no OpenCode build for $(uname -m)"; return 1; }
  meta=$(curl -fsSL --max-time 60 "$OS_ENGINE_REGISTRY/$pkg/$version") || { os_warn "no $pkg $version on the registry"; return 1; }
  url=$(jq -r '.dist.tarball' <<<"$meta")
  want=$(jq -r '.dist.integrity' <<<"$meta")
  tmp=$(mktemp -d)
  if ! curl -fsSL --max-time 900 "$url" -o "$tmp/pkg.tgz"; then
    rm -rf "$tmp"
    os_warn "download failed: $url"
    return 1
  fi
  got="sha512-$(sha512sum "$tmp/pkg.tgz" | cut -c1-128 | tr 'a-f' 'A-F' | basenc --base16 -d | base64 -w0)"
  if [[ $got != "$want" ]]; then
    rm -rf "$tmp"
    os_warn "$pkg $version: the download does not match the registry's sha512 — refused"
    return 1
  fi
  tar -xzf "$tmp/pkg.tgz" -C "$tmp" package/bin/opencode
  mkdir -p "$dest/bin"
  install -m 0755 "$tmp/package/bin/opencode" "$dest/bin/opencode"
  printf '%s %s %s\n' "$pkg" "$version" "$want" >"$dest/PACKAGE"
  rm -rf "$tmp"
}

# os_engine_verify BIN — the engine contract (bashos opencode verify), from the layer's venv.
# BASHOS_ENGINE_VERIFIER names another command taking BIN (the OS tests' stand-in).
os_engine_verify() {
  if [[ -n ${BASHOS_ENGINE_VERIFIER:-} ]]; then
    "$BASHOS_ENGINE_VERIFIER" "$1"
    return
  fi
  local bashos="$BASHOS_OS_PATH/.venv/bin/bashos"
  [[ -x $bashos ]] || bashos="$OS_SRC/.venv/bin/bashos"
  [[ -x $bashos ]] || { os_warn "no bashos to verify with (the runtime's .venv)"; return 1; }
  "$bashos" opencode verify --binary "$1"
}

os_engine_state() { # VERDICT VERSION DETAIL
  os_dry && return 0
  printf 'checked=%s\nverdict=%s\nversion=%s\ndetail=%s\n' "$(date -Is)" "$1" "${2:-}" "${3:-}" |
    os_write_file "$OS_ENGINE_STATE" >/dev/null
}

# bashOS's own copy on PATH, unless that name belongs to something else.
os_engine_link() {
  local link target
  link=$(os_path /usr/local/bin/opencode)
  target=$(readlink "$link" 2>/dev/null || true)
  if [[ -e $link && ! -L $link ]]; then
    os_log "${_os_d}left alone${_os_0} /usr/local/bin/opencode (not a symlink; bashOS runs $OS_ENGINE_BIN)"
  elif [[ -L $link && $target != "$OS_ENGINE_BIN" && $target != */node_modules/opencode-ai/* ]]; then
    os_log "${_os_d}left alone${_os_0} /usr/local/bin/opencode -> $target (bashOS runs $OS_ENGINE_BIN)"
  else
    # absent, ours, or the npm copy older images installed
    os_link "$OS_ENGINE_BIN" /usr/local/bin/opencode
  fi
  printf '%s\n' "$OS_ENGINE_BIN" | os_write_file "$OS_ENGINE_RECORD"
}

# os_engine_install VERSION — fetch, verify (except inside an image build: the boot test runs the
# contract there), then switch `current` to it in one rename and keep the previous release.
os_engine_install() {
  local version=$1 stage home prev
  stage=$(mktemp -d)
  os_engine_fetch "$version" "$stage" || { rm -rf "$stage"; os_engine_state unreachable "$version" "fetch failed"; return 1; }
  if ! os_image && ! os_engine_verify "$stage/bin/opencode"; then
    rm -rf "$stage"
    os_engine_state rejected "$version" "failed the engine contract (bashos opencode verify)"
    os_warn "opencode $version failed the engine contract — not installed"
    return 1
  fi
  home=$(os_path "$OS_ENGINE_HOME")
  prev=$(readlink "$home/current" 2>/dev/null || true)
  os_root mkdir -p "$home"
  os_root rm -rf "$home/$version"
  os_root cp -R "$stage" "$home/$version"
  os_fake_root || os_root chown -R 0:0 "$home/$version"
  # mktemp made the stage 0700: everyone runs the engine, only root changes it
  os_root chmod -R u=rwX,go=rX "$home/$version"
  os_root ln -sfn "$version" "$home/current.new"
  os_root mv -T "$home/current.new" "$home/current"
  rm -rf "$stage"
  # Keep the release before this one, for a rollback; drop the rest.
  local d
  for d in "$home"/*/; do
    d=$(basename "$d")
    [[ $d == "$version" || $d == "$prev" || $d == current ]] || os_root rm -rf "${home:?}/$d"
  done
  os_engine_link
  os_engine_state ok "$version" "verified"
  os_ok "opencode $version (was ${prev:-none}) — fetched, verified, promoted"
}

# Bring the managed engine to npm's latest, or as near as the contract allows.
os_engine_update() {
  local latest current target
  # A fake root never reaches the real registry, only one a test names.
  if os_fake_root && [[ -z ${BASHOS_ENGINE_REGISTRY:-} ]]; then
    os_log "${_os_d}skip (fake root):${_os_0} fetch opencode (latest) into $OS_ENGINE_HOME, verify, promote"
    return 0
  fi
  current=$(os_engine_current)
  if ! latest=$(os_engine_latest 2>/dev/null) || [[ -z $latest ]]; then
    os_warn "the npm registry did not answer — kept opencode ${current:-none}"
    os_engine_state unreachable "$current" "registry unreachable"
    return 0
  fi
  if [[ $current == "$latest" ]]; then
    os_log "${_os_d}unchanged${_os_0} opencode $current (npm latest)"
    os_engine_link
    os_engine_state ok "$current" "latest"
    return 0
  fi
  if os_dry; then
    os_run "fetch opencode $latest ($(os_engine_package)), verify, promote (now: ${current:-none})"
    return 0
  fi
  os_engine_install "$latest" && return 0
  # A new major the contract rejects (OpenCode 2, bamr87/bashos#71) must not freeze the machine:
  # take the newest release of the major it runs.
  local major=${current%%.*}
  [[ -n $current ]] || major=1
  if [[ ${latest%%.*} != "$major" ]] && target=$(os_engine_newest_in "$major") && [[ -n $target && $target != "$current" ]]; then
    os_log "npm latest is opencode $latest (a new major the contract rejects) — newest $major.x is $target"
    os_engine_install "$target" && os_engine_state ok "$target" "newest $major.x; $latest rejected (bamr87/bashos#71)"
  fi
  return 0
}

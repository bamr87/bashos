# os/lib.sh — helpers shared by os.sh, install.sh, the install phases and os/bin. Sourced, never run.
# shellcheck shell=bash
#
# Every change the OS layer makes to a machine goes through one of these helpers, so three
# switches hold everywhere:
#   BASHOS_OS_DRY_RUN=1   print each change as `would:` and make none
#   BASHOS_OS_ROOT=DIR    a fake root: system paths land under DIR, privileged verbs are skipped
#                         (tests, and anything that is not the real machine)
#   BASHOS_OS_IMAGE=1     inside an image build's chroot: no service is started, nothing waits
#                         on a running systemd, the user phases are deferred to first boot

# The tree this code runs from (the repository root, one level above os/).
OS_SRC="${OS_SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OS_DIR="$OS_SRC/os"

BASHOS_OS_ROOT="${BASHOS_OS_ROOT:-}"
BASHOS_OS_DRY_RUN="${BASHOS_OS_DRY_RUN:-0}"
BASHOS_OS_IMAGE="${BASHOS_OS_IMAGE:-0}"
# Where the layer is installed on the machine: the bashOS checkout every link points into.
BASHOS_OS_PATH="${BASHOS_OS_PATH:-/opt/bashos}"
BASHOS_OS_REPO="${BASHOS_OS_REPO:-https://github.com/bamr87/bashos}"

# Markers for the blocks bashOS owns inside a user's dotfiles. Everything outside them is the
# user's and is never rewritten (the same contract as chui's local.zsh block).
OS_BEGIN="# >>> bashos os managed — bashos os uninstall removes this block >>>"
OS_END="# <<< bashos os managed <<<"

if [[ -t 1 && -z ${NO_COLOR:-} ]]; then
  _os_b=$'\e[1m' _os_d=$'\e[2m' _os_g=$'\e[32m' _os_y=$'\e[33m' _os_r=$'\e[31m' _os_0=$'\e[0m'
else
  _os_b="" _os_d="" _os_g="" _os_y="" _os_r="" _os_0=""
fi

os_step() { printf '\n%s== %s ==%s\n' "$_os_b" "$*" "$_os_0"; }
os_log() { printf '  %s\n' "$*"; }
os_ok() { printf '  %s✓%s %s\n' "$_os_g" "$_os_0" "$*"; }
os_warn() { printf '  %s!%s %s\n' "$_os_y" "$_os_0" "$*" >&2; }
os_die() {
  printf '%sbashos os: %s%s\n' "$_os_r" "$*" "$_os_0" >&2
  exit 1
}

os_dry() { [[ $BASHOS_OS_DRY_RUN == 1 ]]; }
os_fake_root() { [[ -n $BASHOS_OS_ROOT ]]; }
os_image() { [[ $BASHOS_OS_IMAGE == 1 ]]; }
os_has() { command -v "$1" >/dev/null 2>&1; }
# os_user_bins HOME — where a person's own tools live, off the system PATH: fnm's default Node,
# ~/.local/bin (claude), ~/.opencode/bin, Volta, mise's shims (Amrchy's Node and agent CLIs).
# Non-interactive shells and systemd units miss them.
os_user_bins() {
  printf '%s\n' "$1/.local/share/fnm/aliases/default/bin" "$1/.local/bin" "$1/.opencode/bin" "$1/.volta/bin" \
    "$1/.local/share/mise/shims"
}
# os_user_has CMD [HOME] — CMD is on PATH or in one of HOME's tool directories.
os_user_has() {
  local d
  os_has "$1" && return 0
  while IFS= read -r d; do [[ -x $d/$1 ]] && return 0; done < <(os_user_bins "${2:-${OS_HOME:-$HOME}}")
  return 1
}
os_is_root() { [[ ${EUID:-$(id -u)} -eq 0 ]]; }

# os_release KEY — one value from the machine's /etc/os-release (under the fake root).
os_release() {
  local f
  f=$(os_path /etc/os-release)
  [[ -r $f ]] || return 0
  sed -n "s/^$1=//p" "$f" | tr -d '"'
}

# os_base — the operating system under the layer:
#   amrchy  Arch with the Amrchy (or upstream Omarchy) framework: bashOS's own base (ADR 0005)
#   arch    Arch without it
#   debian  Debian 13 or a derivative (Raspberry Pi OS): the base ADR 0002 built on
#   other   anything else (a preview only)
os_base() {
  local id like
  id=$(os_release ID) like=$(os_release ID_LIKE)
  if [[ $id == arch || $id == amrchy || $id == omarchy || " $like " == *" arch "* ]]; then
    if [[ -d $(os_path /usr/share/omarchy) || -d $(os_path /usr/share/amrchy) ]]; then
      printf 'amrchy'
    else
      printf 'arch'
    fi
  elif [[ $id == debian || " $like " == *" debian "* ]]; then
    printf 'debian'
  else
    printf 'other'
  fi
}
os_arch_base() { [[ $(os_base) == amrchy || $(os_base) == arch ]]; }

# os_amrchy_version — the framework's version file (Omarchy's runtime ships one), or "unknown".
os_amrchy_version() {
  local d v
  for d in /usr/share/amrchy /usr/share/omarchy; do
    v=$(os_path "$d/version")
    [[ -r $v ]] && { tr -d '\n' <"$v"; return 0; }
  done
  printf 'unknown'
}

# os_console_mode — what BASHOS_CONSOLE means on this machine. `auto` on Amrchy is `desktop`:
# the login screen keeps tty1 and the console opens in a terminal window when the desktop starts.
os_console_mode() {
  local mode=${BASHOS_CONSOLE:-auto}
  if [[ $mode == auto && $(os_base) == amrchy ]]; then
    mode=desktop
  fi
  printf '%s' "$mode"
}

# os_path /etc/x — a system path, under the fake root when there is one.
os_path() { printf '%s%s' "$BASHOS_OS_ROOT" "$1"; }

# os_run CMD… — run a command that changes the machine (or, dry, say it would).
os_run() {
  if os_dry; then
    printf '  %swould:%s %s\n' "$_os_d" "$_os_0" "$*"
    return 0
  fi
  "$@"
}

# os_root CMD… — the same, with root. A fake root needs none: its paths are the caller's own.
os_root() {
  if os_is_root || os_fake_root; then
    os_run "$@"
  elif os_dry; then
    os_run sudo "$@"
  else
    sudo "$@"
  fi
}

# os_systemd_live — a running systemd this process may talk to (never in a chroot or a fake root).
os_systemd_live() { ! os_fake_root && ! os_image && [[ -d /run/systemd/system ]]; }

# os_systemctl ARGS… — the system manager. Offline (an image chroot) only `enable`, `disable`
# and `mask` make sense, and systemctl performs them on unit files without a running manager,
# so `--now` is dropped there. A fake root is never the real machine: nothing is called.
os_systemctl() {
  local args=() a
  for a in "$@"; do
    [[ $a == --now ]] || args+=("$a")
  done
  if os_fake_root; then
    os_log "${_os_d}skip (fake root):${_os_0} systemctl $*"
  elif os_systemd_live; then
    os_root systemctl "$@"
  else
    os_root systemctl "${args[@]}"
  fi
}

# os_user_systemctl USER ARGS… — that user's manager. With a live session bus it is called
# directly; in an image build, `enable`/`disable` become `systemctl --global …` (every user's
# default, which is what an image wants); otherwise the step is reported and skipped.
os_user_systemctl() {
  local user=$1 args=() a
  shift
  for a in "$@"; do
    [[ $a == --now ]] || args+=("$a")
  done
  if os_fake_root; then
    os_log "${_os_d}skip (fake root):${_os_0} systemctl --user $*"
  elif os_image; then
    case ${args[0]} in
      enable | disable) os_run systemctl --global "${args[@]}" ;;
      *) os_log "${_os_d}skip (image build):${_os_0} systemctl --user $*" ;;
    esac
  elif [[ $user == "$(id -un)" ]] && systemctl --user show-environment >/dev/null 2>&1; then
    os_run systemctl --user "$@"
  elif os_is_root && os_systemd_live; then
    os_run systemctl --machine="${user}@" --user "$@"
  else
    os_warn "no user manager for $user — run later: systemctl --user $*"
  fi
}

# os_install_file SRC DEST [MODE] — copy a file bashOS owns into place, only when it differs.
os_install_file() {
  local src=$1 dest mode=${3:-0644}
  dest=$(os_path "$2")
  if [[ -f $dest ]] && cmp -s "$src" "$dest"; then
    os_log "${_os_d}unchanged${_os_0} $2"
    return 0
  fi
  _os_put "$src" "$dest" "$mode" "$2"
  os_dry || os_ok "installed $2"
}

# _os_put SRC DEST MODE SHOWN — the copy itself (mkdir + install: BSD install has no GNU -D).
_os_put() {
  if os_dry; then
    os_run install -m "$3" "$1" "$4"
    return 0
  fi
  os_root mkdir -p "$(dirname "$2")"
  os_root install -m "$3" "$1" "$2"
}

# os_write_file DEST [MODE] < CONTENT — write generated content, only when it differs.
os_write_file() {
  local dest mode=${2:-0644} tmp
  dest=$(os_path "$1")
  tmp=$(mktemp)
  cat >"$tmp"
  if [[ -f $dest ]] && cmp -s "$tmp" "$dest"; then
    rm -f "$tmp"
    os_log "${_os_d}unchanged${_os_0} $1"
    return 0
  fi
  if os_dry; then
    os_run install -m "$mode" "<generated>" "$1"
  else
    _os_put "$tmp" "$dest" "$mode" "$1"
    os_ok "wrote $1"
  fi
  rm -f "$tmp"
}

# os_user_write FILE [MODE] < CONTENT — a file in the user's home that bashOS owns whole (its name
# says so: bashos-*), written as the user, only when it differs.
os_user_write() {
  local file=$1 mode=${2:-0644} tmp
  tmp=$(mktemp)
  cat >"$tmp"
  if [[ -f $file ]] && cmp -s "$tmp" "$file"; then
    rm -f "$tmp"
    os_log "${_os_d}unchanged${_os_0} ${file/#$HOME/\~}"
    return 0
  fi
  if os_dry; then
    os_run install -m "$mode" "<generated>" "${file/#$HOME/\~}"
  else
    mkdir -p "$(dirname "$file")"
    install -m "$mode" "$tmp" "$file"
    os_ok "wrote ${file/#$HOME/\~}"
  fi
  rm -f "$tmp"
}

# os_link TARGET LINK — a symlink bashOS owns (system path).
os_link() {
  local target=$1 link
  link=$(os_path "$2")
  if [[ -L $link && $(readlink "$link") == "$target" ]]; then
    os_log "${_os_d}unchanged${_os_0} $2 -> $target"
    return 0
  fi
  if [[ -e $link && ! -L $link ]]; then
    os_warn "$2 exists and is not a symlink — left alone"
    return 0
  fi
  if os_dry; then
    os_run ln -sfn "$target" "$2"
    return 0
  fi
  os_root mkdir -p "$(dirname "$link")"
  os_root ln -sfn "$target" "$link"
  os_ok "linked $2 -> $target"
}

# os_marks [COMMENT] — the block's two marker lines for a file whose comments start with COMMENT
# (default `#`; Lua is `--`), as OS_MARK_BEGIN and OS_MARK_END.
os_marks() {
  local c=${1:-#}
  OS_MARK_BEGIN="$c${OS_BEGIN#\#}" OS_MARK_END="$c${OS_END#\#}"
}

# _os_block_strip FILE — FILE without the block (markers from os_marks) and without trailing blank
# lines, so the blank line os_block_put puts before a bottom block never accumulates.
_os_block_strip() {
  awk -v b="$OS_MARK_BEGIN" -v e="$OS_MARK_END" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    skip { next }
    $0 == "" { blank++; next }
    { while (blank > 0) { print ""; blank-- } print }
  ' "$1"
}

# os_block_put FILE CONTENT [top|bottom] [COMMENT] — put bashOS's managed block into a user file,
# replacing an earlier copy of the block and keeping every other line. `top` places it first
# (defaults the user's own lines then override); `bottom` (the default) places it last. COMMENT
# is the file's comment leader for the markers (os_marks).
os_block_put() {
  local file=$1 content=$2 where=${3:-bottom} tmp rest
  os_marks "${4:-#}"
  tmp=$(mktemp)
  rest=$(mktemp)
  if [[ -f $file ]]; then
    _os_block_strip "$file" >"$rest"
  fi
  {
    if [[ $where == top ]]; then
      printf '%s\n%s\n%s\n' "$OS_MARK_BEGIN" "$content" "$OS_MARK_END"
      cat "$rest"
    else
      cat "$rest"
      # One blank line between the user's last line and the block.
      [[ -s $rest && -n $(tail -c1 "$rest") ]] && printf '\n'
      [[ -s $rest ]] && printf '\n'
      printf '%s\n%s\n%s\n' "$OS_MARK_BEGIN" "$content" "$OS_MARK_END"
    fi
  } >"$tmp"
  rm -f "$rest"
  if [[ -f $file ]] && cmp -s "$tmp" "$file"; then
    rm -f "$tmp"
    os_log "${_os_d}unchanged${_os_0} ${file/#$HOME/\~}"
    return 0
  fi
  if os_dry; then
    os_run "update the bashos block in ${file/#$HOME/\~}"
    rm -f "$tmp"
    return 0
  fi
  mkdir -p "$(dirname "$file")"
  # cat >, not mv: keep the file's inode, owner and mode (a dotfile may be a symlink chui owns).
  cat "$tmp" >"$file"
  rm -f "$tmp"
  os_ok "updated the bashos block in ${file/#$HOME/\~}"
}

# os_block_drop FILE [COMMENT] — remove bashOS's managed block, keeping every other line.
os_block_drop() {
  local file=$1 tmp
  os_marks "${2:-#}"
  [[ -f $file ]] && grep -qxF -e "$OS_MARK_BEGIN" "$file" || return 0
  if os_dry; then
    os_run "remove the bashos block from ${file/#$HOME/\~}"
    return 0
  fi
  tmp=$(mktemp)
  _os_block_strip "$file" >"$tmp"
  cat "$tmp" >"$file"
  rm -f "$tmp"
  os_ok "removed the bashos block from ${file/#$HOME/\~}"
}

# os_conf_load — the machine's settings: the shipped defaults, then /etc/bashos/os.conf (the
# machine), then ~/.config/bashos/os.conf (the user), then the environment — an exported
# BASHOS_* variable wins over every file (`BASHOS_HARNESS=off bashos os install`).
# Each file is plain KEY=value shell.
os_conf_load() {
  local f env
  # As `export` lines: an eval'd `declare` inside a function would make the variables local.
  env=$(declare -px | sed -n 's/^declare -x \(BASHOS_[A-Za-z0-9_]*=\)/export \1/p')
  local user_home=${BASHOS_USER_HOME:-${HOME:-}}
  for f in "$OS_DIR/config/os.conf" "$(os_path /etc/bashos/os.conf)" ${user_home:+"$user_home/.config/bashos/os.conf"}; do
    # shellcheck source=config/os.conf
    [[ -r $f ]] && source "$f"
  done
  [[ -z $env ]] || eval "$env"
  return 0
}

# os_user — the person this machine is for: $BASHOS_USER, else whoever ran sudo, else $USER.
os_user() {
  if [[ -n ${BASHOS_USER:-} ]]; then
    printf '%s' "$BASHOS_USER"
  elif [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]]; then
    printf '%s' "$SUDO_USER"
  else
    id -un
  fi
}

# os_user_home USER — that user's home directory (a fake root's user lives in $HOME).
os_user_home() {
  local home=""
  if os_fake_root; then
    printf '%s' "$HOME"
    return 0
  fi
  if os_has getent; then
    home=$(getent passwd "$1" 2>/dev/null | cut -d: -f6)
  fi
  if [[ -z $home && $1 == "$(id -un)" ]]; then
    home=$HOME
  fi
  printf '%s' "${home:-/home/$1}"
}

# os_user_shell USER — that user's login shell (basename).
os_user_shell() {
  local shell=""
  if os_has getent; then
    shell=$(getent passwd "$1" 2>/dev/null | cut -d: -f7)
  fi
  basename "${shell:-${SHELL:-/bin/bash}}"
}

# os_loopback HOST — true for an address only this machine can reach.
os_loopback() { [[ $1 == 127.* || $1 == localhost || $1 == ::1 ]]; }

# os_version — what is installed: the checkout's commit, or the build stamp of an image.
os_version() {
  local stamp
  stamp=$(os_path /etc/bashos/build-info)
  if git -C "$BASHOS_OS_PATH" rev-parse --short HEAD >/dev/null 2>&1; then
    git -C "$BASHOS_OS_PATH" describe --tags --always --dirty 2>/dev/null
  elif [[ -r $stamp ]]; then
    sed -n 's/^commit=//p' "$stamp"
  else
    printf 'unknown'
  fi
}

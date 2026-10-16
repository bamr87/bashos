#!/usr/bin/env bash
set -u

_src="${BASH_SOURCE[0]}"
while [[ -L $_src ]]; do
  _dir="$(cd "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ $_src == /* ]] || _src="$_dir/$_src"
done
ROOT="$(cd "$(dirname "$_src")/.." && pwd)"
unset _src _dir

HOME_DIR="${HOME}"
ARCHIVE="${CHUI_HOME_ARCHIVE:-$HOME/Documents/Archive}"
KEEP="${CHUI_HOME_KEEP:-github:bamr87:Claude:Google Drive}"
CANON="Applications Desktop Documents Downloads Library Movies Music Pictures Public"
MAX_KIDS="${CHUI_HOME_KIDS:-8}"
LARGE=$((100 * 1024 * 1024))
COLS="${COLUMNS:-}"
[[ -n $COLS ]] || COLS=$(tput cols 2>/dev/null || echo 80)
SIDE=""
ICONS="${CHUI_ICONS:-auto}"

RED=$'\033[31m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
CYAN=$'\033[36m'
MAGENTA=$'\033[35m'
DIM=$'\033[2m'
BOLD=$'\033[1m'
RST=$'\033[0m'

skip_expand() {
  is_cache "$1" && return 0
  case "$1" in
    Library|Applications|Movies|Music|Pictures|.oh-my-zsh|.rustup|.docker|.ollama|.cursor|.claude|.playwright-mcp|.git-hooks)
      return 0
      ;;
  esac
  return 1
}

hidden_expand() {
  case "$1" in
    .config|.local|.ssh|.chui-backups) return 0 ;;
  esac
  return 1
}

is_canon() {
  case " $CANON " in
    *" $1 "*) return 0 ;;
  esac
  return 1
}

is_keep() {
  is_canon "$1" && return 0
  case ":$KEEP:" in
    *":$1:"*) return 0 ;;
  esac
  return 1
}

is_cache() {
  case "$1" in
    .cache|.npm|.Trash|.DS_Store|.zsh_sessions|.bundle|.gem|.zcompdump*|*.zwc|.wget-hsts) return 0 ;;
  esac
  return 1
}

file_size() {
  local p=$1
  if [[ -f $p && ! -d $p ]]; then
    stat -f %z "$p" 2>/dev/null || stat -c %s "$p" 2>/dev/null || echo 0
  else
    echo 0
  fi
}

human() {
  local n=${1:-0}
  awk -v n="$n" 'BEGIN {
    split("B K M G T", u, " ")
    i=1
    while (n>=1024 && i<5) { n/=1024; i++ }
    if (i==1) printf "%d%s", n, u[i]
    else printf "%.1f%s", n, u[i]
  }'
}

eza_names() {
  local path=$1 mode=$2
  if command -v eza >/dev/null; then
    if [[ $mode == hidden ]]; then
      eza -1A --no-quotes --group-directories-first --color=never "$path" 2>/dev/null | sed 's/ -> .*//' | awk '/^\./ {print}'
    else
      eza -1 --no-quotes --group-directories-first --color=never "$path" 2>/dev/null | sed 's/ -> .*//'
    fi
  else
    if [[ $mode == hidden ]]; then
      command ls -1A "$path" 2>/dev/null | awk '/^\./ {print}'
    else
      command ls -1 "$path" 2>/dev/null
    fi
  fi
}

kid_count() {
  local p=$1
  eza_names "$p" visible | awk 'NF{c++} END{print c+0}'
}

print_kids() {
  local p=$1 indent=$2 color=$3 kind=${4:-visible}
  local kid n i=0 more=0
  local base
  base=$(basename "$p")
  skip_expand "$base" && return 0
  [[ $kind == hidden ]] && { hidden_expand "$base" || return 0; }
  n=$(kid_count "$p")
  [[ $n -gt 0 ]] || return 0
  while IFS= read -r kid; do
    [[ -n $kid ]] || continue
    i=$((i + 1))
    if [[ $i -le $MAX_KIDS ]]; then
      printf '%s%s%s%s\n' "$indent" "$color" "$kid" "$RST"
    else
      more=$((n - MAX_KIDS))
      break
    fi
  done < <(eza_names "$p" visible)
  if [[ $more -gt 0 ]]; then
    printf '%s%s… %s more%s\n' "$indent" "$DIM" "$more" "$RST"
  fi
}

classify_visible() {
  if is_keep "$1"; then
    echo keep
  else
    echo stray
  fi
}

classify_hidden() {
  if is_cache "$1"; then
    echo cache
  else
    echo config
  fi
}

tag_color() {
  case $1 in
    keep) printf '%s' "$GREEN" ;;
    stray) printf '%s' "$RED" ;;
    cache) printf '%s' "$YELLOW" ;;
    config) printf '%s' "$CYAN" ;;
    *) printf '%s' "$RST" ;;
  esac
}

shorten() {
  local s=$1
  local w=${2:-20}
  local n=${#s}
  if [[ $n -gt $w ]]; then
    printf '%s…' "${s:0:$((w - 1))}"
  else
    printf '%s' "$s"
  fi
}

fmt_entry() {
  local base=$1 path=$2 kind=$3
  local tag sz hsz mark n color extra label
  tag=$([[ $kind == hidden ]] && classify_hidden "$base" || classify_visible "$base")
  color=$(tag_color "$tag")
  extra=""
  if [[ -L $path ]]; then
    mark="@"
  elif [[ -d $path ]]; then
    mark="/"
    n=$(kid_count "$path")
    extra=$(printf '%s' "$n")
  else
    mark=""
    sz=$(file_size "$path")
    hsz=$(human "$sz")
    extra=$hsz
    if [[ ${sz:-0} -ge $LARGE ]]; then
      extra="${extra}  LARGE"
    fi
  fi
  label=$(shorten "${base}${mark}" 20)
  printf '%s%-22s%s %s%6s%s %s\n' "$color" "$label" "$RST" "$DIM" "$extra" "$RST" "$tag"
}

render_side() {
  local kind=$1
  local title dumps=0 dump_sz=0
  local base path tag
  if [[ $kind == hidden ]]; then
    title="HIDDEN  (dotfiles you cannot see in Finder)"
  else
    title="VISIBLE  ($HOME_DIR)"
  fi
  printf '%s%s%s\n' "$BOLD$CYAN" "$title" "$RST"
  printf '%s%s%s\n' "$DIM" "$(printf '─%.0s' {1..46})" "$RST"
  while IFS= read -r base; do
    [[ -n $base ]] || continue
    path="$HOME_DIR/$base"
    if [[ $kind == hidden && $base == .zcompdump* ]]; then
      dumps=$((dumps + 1))
      dump_sz=$((dump_sz + $(file_size "$path")))
      continue
    fi
    fmt_entry "$base" "$path" "$kind"
    if [[ -d $path && ! -L $path ]]; then
      print_kids "$path" "    " "$DIM" "$kind"
    fi
  done < <(eza_names "$HOME_DIR" "$kind")
  if [[ $kind == hidden && $dumps -gt 0 ]]; then
    printf '%s%-22s%s %s%6s%s %s\n' "$YELLOW" ".zcompdump* ($dumps)" "$RST" "$DIM" "$(human "$dump_sz")" "$RST" "cache"
  fi
}

render_stray() {
  local base path sz total=0 count=0
  printf '%s%s%s\n' "$BOLD$RED" "STRAY  (does not belong at \$HOME root)" "$RST"
  printf '%s%s%s\n' "$DIM" "$(printf '─%.0s' {1..46})" "$RST"
  while IFS= read -r base; do
    [[ -n $base ]] || continue
    is_keep "$base" && continue
    path="$HOME_DIR/$base"
    count=$((count + 1))
    sz=$(file_size "$path")
    total=$((total + sz))
    fmt_entry "$base" "$path" visible
  done < <(eza_names "$HOME_DIR" visible)
  if [[ $count -eq 0 ]]; then
    printf '%s  clean%s\n' "$GREEN" "$RST"
  else
    printf '\n%s%s items%s  %sloose files %s%s\n' "$RED" "$count" "$RST" "$DIM" "$(human "$total")" "$RST"
    printf '%s  chui home sweep%s  →  %s\n' "$YELLOW" "$RST" "$ARCHIVE"
  fi
}

join_cols() {
  local left=$1 right=$2
  python3 - "$left" "$right" "$COLS" <<'PY'
import sys
from pathlib import Path
left, right, cols = Path(sys.argv[1]).read_text().splitlines(), Path(sys.argv[2]).read_text().splitlines(), int(sys.argv[3])
half = max(40, (cols - 3) // 2)
ansi = __import__("re").compile(r"\x1b\[[0-9;]*m")
def vis(s): return len(ansi.sub("", s))
def pad(s, w):
    n = vis(s)
    if n > w:
        raw, acc, out = s, 0, []
        i = 0
        while i < len(raw) and acc < w - 1:
            if raw[i] == "\x1b":
                m = ansi.match(raw, i)
                if m:
                    out.append(m.group(0)); i = m.end(); continue
            out.append(raw[i]); acc += 1; i += 1
        return "".join(out) + "…"
    return s + " " * (w - n)
n = max(len(left), len(right))
left += [""] * (n - len(left))
right += [""] * (n - len(right))
for a, b in zip(left, right):
    print(pad(a, half) + " │ " + pad(b, half))
PY
}

header() {
  local vis hid stray loose=0
  vis=$(eza_names "$HOME_DIR" visible | awk 'NF{c++} END{print c+0}')
  hid=$(eza_names "$HOME_DIR" hidden | awk 'NF{c++} END{print c+0}')
  stray=0
  while IFS= read -r base; do
    [[ -n $base ]] || continue
    is_keep "$base" && continue
    stray=$((stray + 1))
    loose=$((loose + $(file_size "$HOME_DIR/$base")))
  done < <(eza_names "$HOME_DIR" visible)
  printf '%sCHUI HOME%s  %s  %svis %s%s  %shid %s%s  %sstray %s%s  %sloose %s%s\n' \
    "$BOLD$CYAN" "$RST" "$HOME_DIR" \
    "$GREEN" "$vis" "$RST" \
    "$CYAN" "$hid" "$RST" \
    "$RED" "$stray" "$RST" \
    "$YELLOW" "$(human "$loose")" "$RST"
}

map_full() {
  header
  echo
  if [[ -n $SIDE ]]; then
    case $SIDE in
      visible) render_side visible ;;
      hidden) render_side hidden ;;
      stray) render_stray ;;
      *) render_side visible; echo; render_side hidden; echo; render_stray ;;
    esac
    return 0
  fi
  if [[ ${COLS:-0} -ge 120 ]] && command -v python3 >/dev/null; then
    local tmp
    tmp=$(mktemp -d)
    render_side visible >"$tmp/v"
    render_side hidden >"$tmp/h"
    join_cols "$tmp/v" "$tmp/h"
    rm -rf "$tmp"
    echo
    render_stray
  else
    render_side visible
    echo
    render_side hidden
    echo
    render_stray
  fi
}

do_open() {
  local layout="$ROOT/config/zellij/layouts/home.kdl"
  if ! command -v zellij >/dev/null; then
    map_full
    return 0
  fi
  if [[ -n ${ZELLIJ:-} ]]; then
    map_full
    return 0
  fi
  cd "$HOME_DIR"
  exec zellij --layout "$layout"
}

do_sweep() {
  local base path dest picks="" n=0
  dest="$ARCHIVE/$(date +%Y-%m-%d)"
  local tmp
  tmp=$(mktemp)
  while IFS= read -r base; do
    [[ -n $base ]] || continue
    is_keep "$base" && continue
    printf '%s\n' "$base" >>"$tmp"
    n=$((n + 1))
  done < <(eza_names "$HOME_DIR" visible)
  if [[ $n -eq 0 ]]; then
    printf '%shome is clean — nothing to sweep%s\n' "$GREEN" "$RST"
    rm -f "$tmp"
    return 0
  fi
  if command -v fzf >/dev/null; then
    picks=$(fzf -m --prompt 'sweep> ' --header "move out of $HOME_DIR  →  $dest" \
      --preview "eza -lah --icons=${ICONS} --color=always --group-directories-first $HOME_DIR/{} 2>/dev/null" <"$tmp") || true
  else
    picks=$(cat "$tmp")
  fi
  rm -f "$tmp"
  [[ -n $picks ]] || { echo "cancelled"; return 0; }
  printf 'archive to %s\n' "$dest"
  printf '%s\n' "$picks"
  if command -v gum >/dev/null; then
    gum confirm "move $(printf '%s\n' "$picks" | awk 'NF{c++} END{print c+0}') item(s)?" || return 0
  else
    printf 'move? [y/N] '
    read -r ans
    [[ ${ans:-} == [yY] ]] || return 0
  fi
  mkdir -p "$dest"
  while IFS= read -r base; do
    [[ -n $base ]] || continue
    path="$HOME_DIR/$base"
    [[ -e $path || -L $path ]] || continue
    mv -n "$path" "$dest/"
    printf '%smoved%s  %s  →  %s\n' "$GREEN" "$RST" "$base" "$dest"
  done <<<"$picks"
}

usage() {
  cat <<EOF
chui home              map \$HOME + next level (two columns when maximized)
chui home map          same
chui home map visible  visible side only
chui home map hidden   hidden side only
chui home map stray    stray files only
chui home open         zellij layout (maximize the window first)
chui home sweep        move strays to ${ARCHIVE}

keep: macOS folders + ${KEEP}
override: CHUI_HOME_KEEP  CHUI_HOME_ARCHIVE  CHUI_HOME_MAP=1
EOF
}

cmd=${1:-map}
case $cmd in
  map|"")
    SIDE=${2:-}
    map_full
    ;;
  open) do_open ;;
  sweep) do_sweep ;;
  help|-h|--help) usage ;;
  visible|hidden|stray)
    SIDE=$cmd
    map_full
    ;;
  *)
    printf 'unknown: %s\n' "$cmd" >&2
    usage >&2
    exit 2
    ;;
esac

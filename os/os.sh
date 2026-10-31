#!/usr/bin/env bash
# bashos os — the OS layer's one dispatch table. On PATH as /usr/local/bin/bashos-os; also
# `bashos os …` (bin/bashos runs it before any virtualenv exists, like chui).
set -Eeuo pipefail

_src="${BASH_SOURCE[0]}"
while [[ -L $_src ]]; do
  _dir="$(cd "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ $_src == /* ]] || _src="$_dir/$_src"
done
OS_SRC="$(cd "$(dirname "$_src")/.." && pwd)"
unset _src _dir
# shellcheck source=lib.sh
source "$OS_SRC/os/lib.sh"

usage() {
  cat <<'EOF'
usage: bashos os <command>

  install [-n] [...]      turn this Debian 13 machine into a bashOS machine (install --help)
  update [-n] [--system]  pull the layer, re-apply it, run pending migrations (--system: apt too)
  migrate [--pending]     run pending migrations (--pending: list them; exit 1 when none)
  status                  what is running, as [ OK ]/[WARN]/[CRIT] verdicts (exit = worst)
  harness <verb>          start | stop | restart | status | logs | url
  console                 attach the shared tmux console (what tty1 shows)
  heal                    add a missing bashos window to the console (the timer's job)
  uninstall [-n] [--purge]  remove what install added (--purge: /opt/bashos and /etc/bashos too)
  image <verb>            build | test — the bootable image (os/image/README.md)
  version                 the installed layer's version
EOF
}

# ---------------------------------------------------------------------------- status

STATUS=0
verdict() {
  printf '[%s] %-10s %s\n' "$1" "$2" "$3"
  case $1 in
    CRIT) STATUS=2 ;;
    WARN) ((STATUS >= 1)) || STATUS=1 ;;
  esac
}

cmd_status() {
  os_conf_load
  local v session=${BASHOS_CONSOLE_SESSION:-console} port=${BASHOS_HARNESS_PORT:-4001} code
  printf 'bashos os status · %s · %s\n\n' "$(hostname 2>/dev/null)" "$(date '+%Y-%m-%d %H:%M')"

  if [[ -x $BASHOS_OS_PATH/os/os.sh ]]; then
    verdict " OK " layer "$BASHOS_OS_PATH $(os_version)"
  else
    verdict CRIT layer "nothing at $BASHOS_OS_PATH — run: bashos os install"
  fi
  if v=$("$BASHOS_OS_PATH/.venv/bin/python" -c 'import bashos; print(bashos.__version__)' 2>/dev/null); then
    verdict " OK " runtime "bashos $v ($BASHOS_OS_PATH/.venv)"
  else
    verdict CRIT runtime "no working $BASHOS_OS_PATH/.venv"
  fi
  if os_has opencode || [[ -x $HOME/.opencode/bin/opencode ]]; then
    verdict " OK " engine "opencode $(opencode --version 2>/dev/null || "$HOME/.opencode/bin/opencode" --version 2>/dev/null | head -1)"
  else
    verdict CRIT engine "no opencode on PATH (npm i -g opencode-ai)"
  fi
  if [[ -n ${CLAUDE_CODE_OAUTH_TOKEN:-} ]]; then
    verdict " OK " auth "CLAUDE_CODE_OAUTH_TOKEN"
  elif [[ -f $HOME/.claude/.credentials.json ]]; then
    verdict " OK " auth "Claude Code login (~/.claude)"
  elif [[ -n ${ANTHROPIC_API_KEY:-} ]]; then
    verdict " OK " auth "ANTHROPIC_API_KEY (fallback)"
  else
    verdict WARN auth "no Claude credential — run: claude (sign in once)"
  fi

  if [[ ${BASHOS_CONSOLE:-auto} == off ]]; then
    verdict " OK " console "off (BASHOS_CONSOLE=off)"
  elif tmux has-session -t "=$session" 2>/dev/null; then
    local windows clients
    windows=$(tmux list-windows -t "=$session" -F '#{window_name}' | paste -sd, -)
    clients=$(tmux list-clients -t "=$session" 2>/dev/null | wc -l | tr -d ' ')
    if [[ ,$windows, == *,bashos,* ]]; then
      verdict " OK " console "session $session: $windows · $clients client(s)"
    else
      verdict WARN console "session $session has no bashos window (bashos os heal)"
    fi
  else
    verdict WARN console "no tmux session '$session' (the monitor attaches it at login)"
  fi

  if [[ ${BASHOS_HARNESS:-native} == off ]]; then
    verdict " OK " harness "off (BASHOS_HARNESS=off)"
  else
    local state
    state=$(systemctl --user is-active bashos-harness.service 2>/dev/null || true)
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$port/api/health" 2>/dev/null || true)
    if [[ $code == 200 ]]; then
      verdict " OK " harness "${BASHOS_HARNESS:-native} · ${state:-unknown} · http://${BASHOS_HARNESS_HOST:-127.0.0.1}:$port/ answers"
    elif [[ $state == activating || $state == active ]]; then
      verdict WARN harness "$state, :$port not answering yet (a first start builds the page) — bashos os harness logs"
    else
      verdict CRIT harness "${state:-not running}, :$port silent — bashos os harness logs"
    fi
  fi
  if systemctl --user is-active --quiet bashos-heal.timer 2>/dev/null; then
    verdict " OK " heal "bashos-heal.timer active"
  else
    verdict WARN heal "bashos-heal.timer inactive (systemctl --user enable --now bashos-heal.timer)"
  fi
  if [[ -f /var/lib/bashos/provisioned ]]; then
    verdict " OK " provision "first boot done $(cat /var/lib/bashos/provisioned)"
  fi
  return "$STATUS"
}

# ---------------------------------------------------------------------------- update + migrate

cmd_migrate() {
  local state="$HOME/.local/state/bashos/migrations" m name pending=()
  for m in "${BASHOS_OS_MIGRATIONS:-$OS_DIR/migrations}"/*.sh; do
    [[ -f $m ]] || continue
    name=$(basename "$m")
    [[ -f $state/$name ]] || pending+=("$m")
  done
  if [[ ${1:-} == --pending ]]; then
    ((${#pending[@]})) || return 1
    printf '%s\n' "${pending[@]##*/}"
    return 0
  fi
  if ((!${#pending[@]})); then
    os_ok "no pending migrations"
    return 0
  fi
  mkdir -p "$state"
  for m in "${pending[@]}"; do
    name=$(basename "$m")
    os_step "migration $name"
    if os_dry; then
      os_run bash "$m"
      continue
    fi
    OS_SRC="$OS_SRC" bash "$m" || os_die "migration $name failed — fix it, then: bashos os migrate"
    : >"$state/$name"
    os_ok "$name"
  done
}

cmd_update() {
  local system=0 path=$BASHOS_OS_PATH
  while (($#)); do
    case $1 in
      -n | --dry-run) export BASHOS_OS_DRY_RUN=1 ;;
      --system) system=1 ;;
      *) os_die "usage: bashos os update [-n] [--system]" ;;
    esac
    shift
  done
  os_conf_load
  local channel=${BASHOS_CHANNEL:-main}
  os_step "layer ($path ← $BASHOS_OS_REPO $channel)"
  if [[ -d $path/.git ]]; then
    os_root git -C "$path" fetch --quiet origin "$channel"
    os_root git -C "$path" merge --ff-only --quiet FETCH_HEAD
  else
    # An image's layer is a staged copy: make it a checkout of the channel (ignored files such
    # as .venv stay; files the channel no longer has go).
    os_root git -C "$path" init --quiet
    os_root git -C "$path" remote add origin "$BASHOS_OS_REPO" 2>/dev/null || true
    os_root git -C "$path" fetch --quiet --depth 1 origin "$channel"
    os_root git -C "$path" reset --quiet --hard FETCH_HEAD
    os_root git -C "$path" clean -fdq
  fi
  os_dry || os_ok "layer at $(os_version)"
  if ((system)); then
    os_step "system packages"
    os_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    os_root env DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade
  fi
  # The freshly pulled code re-applies itself, then brings this install forward.
  local flags=()
  os_dry && flags=(--dry-run)
  "$path/os/install.sh" "${flags[@]}"
  "$path/os/os.sh" migrate
  if ! os_dry && systemctl --user is-active --quiet bashos-harness.service 2>/dev/null; then
    systemctl --user restart bashos-harness.service
    os_ok "harness restarted"
  fi
}

# ---------------------------------------------------------------------------- harness, console

cmd_harness() {
  os_conf_load
  local port=${BASHOS_HARNESS_PORT:-4001}
  case ${1:-status} in
    start | stop | restart) systemctl --user "$1" bashos-harness.service ;;
    status) systemctl --user --no-pager status bashos-harness.service ;;
    logs) journalctl --user -u bashos-harness.service -n 200 -f ;;
    url)
      printf 'http://%s:%s/\n' "${BASHOS_HARNESS_HOST:-127.0.0.1}" "$port"
      os_loopback "${BASHOS_HARNESS_HOST:-127.0.0.1}" &&
        printf 'from another machine: ssh -L %s:127.0.0.1:%s %s, then http://127.0.0.1:%s/\n' "$port" "$port" "$(hostname)" "$port"
      ;;
    *) os_die "usage: bashos os harness start|stop|restart|status|logs|url" ;;
  esac
}

# ---------------------------------------------------------------------------- uninstall

cmd_uninstall() {
  local purge=0 f l
  while (($#)); do
    case $1 in
      -n | --dry-run) export BASHOS_OS_DRY_RUN=1 ;;
      --purge) purge=1 ;;
      *) os_die "usage: bashos os uninstall [-n] [--purge]" ;;
    esac
    shift
  done
  os_step "user"
  if ! os_dry; then
    systemctl --user disable --now bashos-harness.service bashos-heal.timer 2>/dev/null || true
  else
    os_run systemctl --user disable --now bashos-harness.service bashos-heal.timer
  fi
  for f in .zprofile .bash_profile .profile .zshrc .bashrc .tmux.conf; do
    os_block_drop "$HOME/$f"
  done
  os_step "system"
  for l in /usr/local/bin/bashos /usr/local/bin/os-health /usr/local/bin/bashos-os /usr/local/bin/bashos-console \
    /usr/local/bin/bashos-harness /usr/local/sbin/bashos-provision; do
    [[ -L $(os_path "$l") && $(readlink "$(os_path "$l")") == "$BASHOS_OS_PATH"/* ]] && os_root rm -f "$(os_path "$l")"
  done
  for f in "$(os_path /usr/local/lib/systemd)"/{system,user}/bashos-* \
    "$(os_path /etc/systemd/system/getty@tty1.service.d/bashos-autologin.conf)" \
    "$(os_path /etc/systemd/logind.conf.d/bashos-no-sleep.conf)"; do
    [[ -e $f ]] && os_root rm -f "$f"
  done
  os_systemd_live && os_root systemctl daemon-reload
  if ((purge)); then
    os_root rm -rf "$(os_path "$BASHOS_OS_PATH")" "$(os_path /etc/bashos)"
  fi
  os_log "kept: the hub checkout, linger, masked sleep targets$( ((purge)) || printf ', %s and /etc/bashos (--purge removes them)' "$BASHOS_OS_PATH")"
  os_dry && printf '\n%sdry run: nothing was changed%s\n' "$_os_b" "$_os_0"
  return 0
}

# ---------------------------------------------------------------------------- dispatch

cmd=${1:-help}
(($#)) && shift
case $cmd in
  install) exec "$OS_DIR/install.sh" "$@" ;;
  update) cmd_update "$@" ;;
  migrate) cmd_migrate "$@" ;;
  status) cmd_status ;;
  harness) cmd_harness "$@" ;;
  console) exec "$OS_DIR/bin/bashos-console" --attach ;;
  heal) exec "$OS_DIR/bin/bashos-console" --heal ;;
  uninstall) cmd_uninstall "$@" ;;
  image)
    case ${1:-} in
      build) shift; exec "$OS_DIR/image/build.sh" "$@" ;;
      test) shift; exec "$OS_DIR/image/test/boot-smoke.sh" "$@" ;;
      *) os_die "usage: bashos os image build|test [options] (os/image/README.md)" ;;
    esac
    ;;
  version) printf 'bashos os %s (%s)\n' "$(os_version)" "$BASHOS_OS_PATH" ;;
  help | -h | --help) usage ;;
  *) usage >&2; exit 2 ;;
esac

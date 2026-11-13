# os/install/harness.sh — the bamr87 hub checkout and the Harness Console service. The checkout
# is the user's: an existing tree (forge keeps an rsync copy) is never touched.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

phase_harness() {
  os_step "harness"
  local mode=${BASHOS_HARNESS:-native} hub=${BASHOS_HUB_DIR:-$OS_HOME/dev/bamr87} env_file
  hub=${hub/#\~/$OS_HOME}
  if [[ $mode == off ]]; then
    os_log "harness off (BASHOS_HARNESS=off)"
    os_user_systemctl "$OS_USER" disable --now bashos-harness.service
    return 0
  fi

  if [[ -d $hub/tools/console ]]; then
    os_ok "hub checkout at ${hub/#$OS_HOME/\~}"
  elif [[ -e $hub ]]; then
    os_warn "${hub/#$OS_HOME/\~} exists but has no tools/console — left alone; set BASHOS_HUB_DIR"
  elif os_fake_root; then
    os_log "${_os_d}skip (fake root):${_os_0} git clone --depth 1 ${BASHOS_HUB_REPO:-https://github.com/bamr87/bamr87} $hub"
  else
    os_run mkdir -p "$(dirname "$hub")"
    # The root only: the console reads the hub's own tools/ and _data/, never the submodules.
    os_run git clone --quiet --depth 1 "${BASHOS_HUB_REPO:-https://github.com/bamr87/bamr87}" "$hub"
    os_dry || os_ok "cloned the hub into ${hub/#$OS_HOME/\~}"
  fi

  # Secrets for the console live here, never in os.conf: mode 0600, created once, never rewritten.
  env_file="$OS_HOME/.config/bashos/harness.env"
  if [[ -f $env_file ]]; then
    os_log "${_os_d}kept${_os_0} ${env_file/#$OS_HOME/\~}"
  elif os_dry; then
    os_run "create ${env_file/#$OS_HOME/\~} (0600)"
  else
    mkdir -p "$(dirname "$env_file")"
    (umask 077 && cat >"$env_file" <<'ENV'
# Environment for bashos-harness — the hub's Harness Console. Mode 0600; never committed.
# Required before BASHOS_HARNESS_HOST is a LAN address: the bearer token every /api call needs.
#DASH_CONSOLE_TOKEN=
# GitHub for the console's operations (or sign in on its Credentials page):
#GH_TOKEN=
ENV
    )
    os_ok "created ${env_file/#$OS_HOME/\~} (0600)"
  fi

  # A start before the hub existed left the unit failed (exit 78): clear it, then (re)start.
  os_user_systemctl "$OS_USER" reset-failed bashos-harness.service 2>/dev/null || true
  os_user_systemctl "$OS_USER" enable --now bashos-harness.service bashos-heal.timer
  os_log "harness: $mode on ${BASHOS_HARNESS_HOST:-127.0.0.1}:${BASHOS_HARNESS_PORT:-4001} — bashos os harness status"
}

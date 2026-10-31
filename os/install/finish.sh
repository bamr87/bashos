# os/install/finish.sh — the migration baseline, then what to do next.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

phase_finish() {
  os_step "finish"
  local state="$OS_HOME/.local/state/bashos/migrations" m n=0
  # A fresh install is already current: every shipped migration counts as applied (they exist
  # to bring OLDER installs forward). An existing state directory is left to `bashos os migrate`.
  if [[ -d $state ]]; then
    os_log "${_os_d}kept${_os_0} migration state ($(find "$state" -type f | wc -l | tr -d ' ') applied)"
  elif os_dry; then
    os_run "mark $(find "${BASHOS_OS_MIGRATIONS:-$OS_DIR/migrations}" -name '*.sh' | wc -l | tr -d ' ') migrations applied (fresh install)"
  else
    mkdir -p "$state"
    for m in "${BASHOS_OS_MIGRATIONS:-$OS_DIR/migrations}"/*.sh; do
      [[ -f $m ]] || continue
      : >"$state/$(basename "$m")"
      n=$((n + 1))
    done
    os_ok "migration baseline: $n applied"
  fi

  printf '\n%sbashOS is installed.%s\n' "$_os_b" "$_os_0"
  printf '  bashos os status          what is running, as verdicts\n'
  printf '  bashos                    the desktop (it is also window 1 of the tmux console)\n'
  printf '  ssh -L %s:127.0.0.1:%s %s    the Harness Console from another machine\n' \
    "${BASHOS_HARNESS_PORT:-4001}" "${BASHOS_HARNESS_PORT:-4001}" "$(hostname 2>/dev/null || echo HOST)"
  if [[ ! -f $OS_HOME/.claude/.credentials.json && -z ${CLAUDE_CODE_OAUTH_TOKEN:-} ]]; then
    printf '  claude                    sign in once: bashOS wires that credential into the engine\n'
  fi
}

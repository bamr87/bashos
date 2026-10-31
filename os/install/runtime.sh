# os/install/runtime.sh — the layer at $BASHOS_OS_PATH, its .venv, the engine CLIs, and the
# commands on /usr/local/bin (absolute paths: tmux panes and systemd units get a bare PATH).
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

# The layer is root-owned on purpose: the platform is not writable by the user's processes
# (or the agents they run). `bashos os update` changes it, through sudo.
os_deploy_layer() {
  local dst src_real dst_real
  dst=$(os_path "$BASHOS_OS_PATH")
  src_real=$(cd "$OS_SRC" && pwd -P)
  dst_real=$(cd "$dst" 2>/dev/null && pwd -P || true)
  if [[ $src_real == "$dst_real" ]]; then
    os_ok "the layer runs from $BASHOS_OS_PATH"
    return 0
  fi
  if [[ -d $dst/.git ]]; then
    os_warn "$BASHOS_OS_PATH is a git checkout — left alone (update it with: bashos os update)"
    return 0
  fi
  if os_dry; then
    os_run rsync -a --delete "$OS_SRC/ (what git would ship)" "$BASHOS_OS_PATH/"
    return 0
  fi
  # Only what git would ship: tracked files plus untracked ones not ignored (.venv, .env, engine
  # state never travel). Without git (a tarball), rsync honours the same .gitignore files.
  # Staged first, so a file the new tree dropped is deleted from the layer too.
  local stage
  stage=$(mktemp -d)
  if git -C "$OS_SRC" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$OS_SRC" ls-files -z -co --exclude-standard | tar -C "$OS_SRC" --null -T - -cf - | tar -C "$stage" -xf -
  else
    rsync -a --filter=':- .gitignore' --exclude=.git --exclude=.venv "$OS_SRC/" "$stage/"
  fi
  local own=()
  os_fake_root || own=(--chown=0:0)
  os_root mkdir -p "$dst"
  os_root rsync -a --delete "${own[@]}" --exclude=/.venv "$stage/" "$dst/"
  rm -rf "$stage"
  os_ok "deployed $OS_SRC -> $BASHOS_OS_PATH"
}

os_build_info() {
  local commit dirty=no
  commit=$(git -C "$OS_SRC" rev-parse HEAD 2>/dev/null || printf '%s' "${BASHOS_BUILD_COMMIT:-unknown}")
  if git -C "$OS_SRC" rev-parse HEAD >/dev/null 2>&1 && [[ -n $(git -C "$OS_SRC" status --porcelain 2>/dev/null) ]]; then
    dirty=yes
  fi
  # A staged image tree carries the stamp the build wrote; keep it.
  if [[ $commit == unknown && -r $(os_path /etc/bashos/build-info) ]]; then
    return 0
  fi
  os_write_file /etc/bashos/build-info <<EOF
commit=$commit
dirty=${BASHOS_BUILD_DIRTY:-$dirty}
source=${BASHOS_BUILD_SOURCE:-$OS_SRC}
layer=$BASHOS_OS_PATH
EOF
}

os_venv() {
  local venv="$BASHOS_OS_PATH/.venv"
  if os_fake_root; then
    os_log "${_os_d}skip (fake root):${_os_0} python3 -m venv $venv && pip install -e $BASHOS_OS_PATH"
    return 0
  fi
  [[ -x $venv/bin/python ]] || os_root python3 -m venv "$venv"
  # Always-latest (fleet policy): every install and update resolves the newest releases.
  os_root "$venv/bin/pip" install --quiet --upgrade pip
  os_root "$venv/bin/pip" install --quiet --upgrade -e "$BASHOS_OS_PATH"
  os_dry || os_ok "$venv (bashos $("$venv/bin/python" -c 'import bashos; print(bashos.__version__)'))"
}

# The engine and the credential source: kept if the user already has them on PATH (forge
# installed opencode under ~/.opencode), else installed system-wide from Debian's npm.
os_engines() {
  local pair cmd pkg npm=/usr/bin/npm
  for pair in "opencode:opencode-ai" "claude:@anthropic-ai/claude-code"; do
    cmd=${pair%%:*} pkg=${pair#*:}
    if ! os_image && { os_has "$cmd" || [[ -x $OS_HOME/.opencode/bin/$cmd || -x $OS_HOME/.local/bin/$cmd ]]; }; then
      os_ok "$cmd present"
      continue
    fi
    if os_fake_root; then
      os_log "${_os_d}skip (fake root):${_os_0} npm install -g --prefix /usr/local $pkg"
      continue
    fi
    if [[ ! -x $npm ]] && ! os_dry; then
      os_warn "no system npm ($npm) — install $cmd yourself: npm i -g $pkg"
      continue
    fi
    os_root "$npm" install -g --prefix /usr/local --no-fund --no-audit --loglevel=error "$pkg"
    os_dry || os_ok "$cmd installed (/usr/local/bin/$cmd)"
  done
}

os_commands() {
  local layer=$BASHOS_OS_PATH
  os_link "$layer/bin/bashos" /usr/local/bin/bashos
  os_link "$layer/bin/os-health" /usr/local/bin/os-health
  os_link "$layer/os/os.sh" /usr/local/bin/bashos-os
  os_link "$layer/os/bin/bashos-console" /usr/local/bin/bashos-console
  os_link "$layer/os/bin/bashos-harness" /usr/local/bin/bashos-harness
  os_link "$layer/os/bin/bashos-provision" /usr/local/sbin/bashos-provision
}

phase_runtime() {
  os_step "runtime"
  os_deploy_layer
  os_build_info
  os_venv
  os_engines
  os_commands
}

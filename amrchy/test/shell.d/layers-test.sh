#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

run_layers() {
  local scope="$1"
  OMARCHY_INSTALL="$tmp/install" OMARCHY_INSTALL_USER=dhh \
    bash -eE -c 'source "$1"' bash "$ROOT/install/$scope/layers.sh"
}

grep -qxF 'run_logged "$OMARCHY_INSTALL/post-install/layers.sh"' "$ROOT/install/post-install/all.sh" ||
  fail "post-install runs the layers' system setup"
grep -qxF 'run_logged "$OMARCHY_INSTALL/user/layers.sh"' "$ROOT/install/user/all.sh" ||
  fail "user setup runs the layers' user setup"
[[ $(tail -n 1 "$ROOT/install/post-install/all.sh") == 'run_logged "$OMARCHY_INSTALL/post-install/layers.sh"' ]] ||
  fail "layers run after the rest of the system setup"
pass "the install lists run the layers last"

mkdir -p "$tmp/install"
output=$(run_layers post-install) || fail "no layers directory is not an error"
[[ -z $output ]] || fail "no layers run without a layers directory" "$output"
pass "no layers, nothing runs"

mkdir -p "$tmp/install/layers/alpha" "$tmp/install/layers/beta" "$tmp/install/layers/gamma"
cat >"$tmp/install/layers/alpha/system.sh" <<'EOF'
printf '%s %s %s\n' "$LAYER_NAME" "${LAYER_DIR##*/}" "$OMARCHY_INSTALL_USER" >>"$LAYER_DIR/../../ran"
EOF
cat >"$tmp/install/layers/gamma/system.sh" <<'EOF'
printf 'gamma\n' >>"$LAYER_DIR/../../ran"
EOF
cat >"$tmp/install/layers/beta/user.sh" <<'EOF'
printf 'beta user\n' >>"$LAYER_DIR/../../ran"
EOF

run_layers post-install >/dev/null || fail "the system runner succeeds"
[[ $(cat "$tmp/install/ran") == $'alpha alpha dhh\ngamma' ]] ||
  fail "each layer's system.sh runs once, in name order, with its name, directory and the install user" "$(cat "$tmp/install/ran")"
pass "system setup runs every layer that has one"

rm "$tmp/install/ran"
run_layers user >/dev/null || fail "the user runner succeeds"
[[ $(cat "$tmp/install/ran") == "beta user" ]] || fail "only user.sh runs for users" "$(cat "$tmp/install/ran")"
pass "user setup runs every layer that has one"

printf 'false\n' >"$tmp/install/layers/alpha/system.sh"
if run_layers post-install >/dev/null 2>&1; then
  fail "a failing layer fails its install step"
fi
pass "a failing layer is not silently skipped"

#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

require_command python3

source "$ROOT/default/bash/brand.sh"
brand_load || fail "brand config loads"
[[ $BRAND_ID == "amrchy" && $BRAND_NAME == "Amrchy" && $BRAND_ENV == "AMRCHY" ]] ||
  fail "brand identity comes from default/brand.toml"
[[ $BRAND_PATH_VAR == "AMRCHY_PATH" ]] || fail "brand path variable is derived from the env prefix"
pass "brand config is the identity source"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/default" "$tmp/tree/foomark"
cat >"$tmp/default/brand.toml" <<'EOF'
[identity]
id = "barmark"
name = "Barmark"
env = "BARMARK"

[previous]
id = "foomark"
name = "Foomark"
env = "FOOMARK"

[substitute]
"https://example.test/foomark.git" = "https://example.test/barmark.git"

[preserve]
patterns = [
  'https?://\S*foomark\.example\S*',
  'foomark-kept',
  '#foomark-help',
]
EOF

printf 'FOOMARK_PATH=/usr/share/foomark\nHello Foomark\n' >"$tmp/tree/note.txt"
printf 'keep foomark-kept and #foomark-help\n' >"$tmp/tree/keep.txt"
printf 'see https://pkgs.foomark.example/stable\n' >"$tmp/tree/url.txt"
printf 'clone https://example.test/foomark.git\n' >"$tmp/tree/clone.txt"
printf 'ownedByFoomark\n' >"$tmp/tree/foomark/readme.txt"
printf 'foomark\x00bin' >"$tmp/tree/foomark.bin"

dry=$(python3 "$ROOT/bin/rebrand" --root "$tmp" --verbose)
[[ $dry == *"content files: 3"* ]] || fail "dry-run counts content rewrites" "$dry"
[[ $dry == *"path renames: 2"* ]] || fail "dry-run counts path renames" "$dry"
[[ -f $tmp/tree/foomark/readme.txt ]] || fail "dry-run does not rename"
grep -q 'FOOMARK_PATH' "$tmp/tree/note.txt" || fail "dry-run does not rewrite content"
pass "dry-run plans the rebrand without writing"

python3 "$ROOT/bin/rebrand" --root "$tmp" --apply --check >/dev/null ||
  fail "apply rewrites the tree and checks clean"
[[ -f $tmp/tree/barmark/readme.txt ]] || fail "directory and file names follow the identity"
[[ ! -e $tmp/tree/foomark ]] || fail "previous directory name is removed"
grep -q 'BARMARK_PATH=/usr/share/barmark' "$tmp/tree/note.txt" || fail "env and path tokens follow the identity"
grep -q 'Hello Barmark' "$tmp/tree/note.txt" || fail "display name follows the identity"
grep -q 'ownedByBarmark' "$tmp/tree/barmark/readme.txt" || fail "embedded display name follows the identity"
grep -q 'foomark-kept' "$tmp/tree/keep.txt" || fail "preserved tokens stay"
grep -q '#foomark-help' "$tmp/tree/keep.txt" || fail "preserved channel names stay"
grep -q 'https://pkgs.foomark.example/stable' "$tmp/tree/url.txt" || fail "preserved urls stay"
grep -q 'https://example.test/barmark.git' "$tmp/tree/clone.txt" || fail "configured url substitutions apply"
grep -q 'foomark' "$tmp/tree/barmark.bin" || fail "binary content is not rewritten"
[[ -f $tmp/tree/barmark.bin && ! -e $tmp/tree/foomark.bin ]] || fail "binary filename still follows the identity"
pass "apply rewrites identity and keeps conflicts"

second=$(python3 "$ROOT/bin/rebrand" --root "$tmp" --apply --check)
[[ $second == *"content files: 0"* && $second == *"path renames: 0"* && $second == *"check: ok"* ]] ||
  fail "rebrand is idempotent" "$second"
pass "rebrand is idempotent"

printf 'foomark leftover\n' >"$tmp/tree/stray.txt"
if python3 "$ROOT/bin/rebrand" --root "$tmp" --check >/dev/null 2>&1; then
  fail "check rejects an unpreserved previous id"
fi
pass "check rejects an unpreserved previous id"

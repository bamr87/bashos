#!/usr/bin/env bash
# make bump: propose new pins (§4). Prints a diff; never commits. CI opens the PR.
source "$(dirname "$0")/lib.sh"
need curl jq python3

cur="$(manifest get ventoy.version)"
latest="$(curl -fsSI https://github.com/ventoy/Ventoy/releases/latest |
  sed -n 's#^location: .*/tag/v\([0-9.]*\).*#\1#Ip' | tr -d '\r')"
new="$ONEOS_ROOT/build/manifest.bump.yaml"
mkdir -p "$(dirname "$new")"
cp "$ONEOS_ROOT/manifest.yaml" "$new"

if [[ -n "$latest" && "$latest" != "$cur" ]]; then
  sum="$(curl -fsSL "https://github.com/ventoy/Ventoy/releases/download/v$latest/sha256.txt" |
    awk -v f="ventoy-$latest-linux.tar.gz" '$2==f{print $1}')"
  [[ ${#sum} -eq 64 ]] || die "could not read checksum for Ventoy $latest"
  sed -i -e "s/$cur/$latest/g" -e "/^ventoy:/,/^[a-z]/ s/sha256: \"[0-9a-f]*\"/sha256: \"$sum\"/" "$new"
  log "Ventoy $cur → $latest"
fi

# Artifacts with sha256_from: refresh the pinned sum from the publisher's list.
while IFS= read -r a; do
  from="$(jq -r '.sha256_from // empty' <<<"$a")"; [[ -n "$from" ]] || continue
  url="$(jq -r .url <<<"$a")"; old="$(jq -r .sha256 <<<"$a")"
  sum="$(curl -fsSL "$from" | awk -v f="$(basename "$url")" '{sub(/^\*/,"",$2)} $2==f{print $1}')"
  if [[ ${#sum} -eq 64 && "$sum" != "$old" ]]; then
    sed -i "s/$old/$sum/" "$new"; log "$(jq -r .name <<<"$a"): new checksum"
  fi
done < <(manifest artifacts)

if diff -u "$ONEOS_ROOT/manifest.yaml" "$new"; then log "no changes"; fi

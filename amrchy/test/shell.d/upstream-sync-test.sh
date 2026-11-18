#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

require_command python3
require_command git

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export HOME="$tmp/home" GIT_CONFIG_NOSYSTEM=1
mkdir -p "$HOME"
git config --global user.name test
git config --global user.email test@example.test
git config --global init.defaultBranch quattro
git config --global advice.detachedHead false

sync() { (cd "$tmp/fork" && python3 "$ROOT/bin/upstream-sync" --no-fetch "$@"); }
commit() { git -C "$1" add -A && git -C "$1" commit -q -m "$2"; }

# Upstream, and a fork with a change of its own.
git init -q "$tmp/up"
echo base >"$tmp/up/shared.txt"
commit "$tmp/up" "Base"
git clone -q "$tmp/up" "$tmp/fork"
git -C "$tmp/fork" switch -q -c main
git -C "$tmp/fork" remote rename origin upstream
mkdir -p "$tmp/fork/default" "$tmp/fork/.upstream"
cat >"$tmp/fork/default/upstream.toml" <<EOF
[upstream]
remote = "upstream"
url = "$tmp/up"
branch = "quattro"

[fork]
branch = "main"

[policy]
fork_owned = ["fork.txt", ".upstream/"]
decline = ['subject:(?i)telemetry']

[checks]
commands = ["test -f shared.txt"]
EOF
printf '# date\tupstream\tdecision\tsubject\treason\n' >"$tmp/fork/.upstream/ledger.tsv"
echo mine >"$tmp/fork/fork.txt"
commit "$tmp/fork" "Fork divergence"

# Upstream moves on: a pull request, a direct fix, and something this fork declines.
git -C "$tmp/up" switch -q -c feature
echo feature >"$tmp/up/feature.txt"
commit "$tmp/up" "Add a feature"
git -C "$tmp/up" switch -q quattro
git -C "$tmp/up" merge -q --no-ff feature -m "Merge pull request #7 from someone/feature" -m "Add a feature"
echo fixed >"$tmp/up/shared.txt"
commit "$tmp/up" "Fix a bug (#8)"
echo ping >"$tmp/up/telemetry.txt"
commit "$tmp/up" "Add telemetry ping"
git -C "$tmp/fork" fetch -q upstream

plan=$(sync plan)
[[ $plan == *"3 pending upstream change(s), 1 flagged"* ]] || fail "plan counts upstream changes" "$plan"
[[ $plan == *"Add a feature"*"/pull/7"* ]] || fail "plan names a pull request by its title" "$plan"
[[ $plan == *"Fix a bug (#8)"*"/pull/8"* ]] || fail "plan finds a direct commit's pull request" "$plan"
[[ $plan == *"DECLINE? subject:(?i)telemetry"* ]] || fail "plan flags a decline candidate" "$plan"
sync plan --json | python3 -c 'import json,sys; c=json.load(sys.stdin); assert [x["pr"] for x in c] == [7, 8, None], c' ||
  fail "plan --json carries each change"
pass "plan lists upstream's changes with policy flags"

sync merge >/dev/null || fail "a clean merge succeeds"
branch=$(git -C "$tmp/fork" rev-parse --abbrev-ref HEAD)
[[ $branch == upstream-sync/* ]] || fail "merge works on a sync branch, not the fork branch" "$branch"
[[ -f $tmp/fork/feature.txt && -f $tmp/fork/fork.txt ]] || fail "the merge keeps both sides"
pass "merge brings upstream onto a sync branch"

telemetry=$(git -C "$tmp/up" rev-parse quattro)
sync decline "$telemetry" -r "this fork ships no telemetry" >/dev/null || fail "decline reverts a change"
[[ ! -e $tmp/fork/telemetry.txt ]] || fail "a declined change is reverted"
git -C "$tmp/fork" log -1 --format=%B | grep -q "Upstream-Declined: $telemetry" || fail "the revert names the upstream commit"
pass "decline leaves an upstream change out, on the record"

sync check >/dev/null || fail "check passes on a clean merge"
report=$(sync finish)
[[ -f $report ]] || fail "finish writes a report" "$report"
grep -q "2 taken, 1 declined" "$report" || fail "the report counts decisions" "$(cat "$report")"
grep -q "this fork ships no telemetry" "$report" || fail "the report gives the reason"
ledger=$(grep -v '^#' "$tmp/fork/.upstream/ledger.tsv")
[[ $(grep -c $'\ttaken\t' <<<"$ledger") == 2 && $(grep -c $'\tdeclined\t' <<<"$ledger") == 1 ]] ||
  fail "the ledger records every decision" "$ledger"
[[ -z $(git -C "$tmp/fork" status --porcelain) ]] || fail "finish commits the ledger"
[[ $(sync plan) == *"nothing pending"* ]] || fail "nothing is pending after a sync"
pass "finish records the sync and writes its report"

# The next sync brings only what is new, and a conflict on a fork-owned path stops it.
git -C "$tmp/fork" switch -q main
git -C "$tmp/fork" merge -q --ff-only "$branch"
echo theirs >"$tmp/up/fork.txt"
commit "$tmp/up" "Upstream adds fork.txt"
git -C "$tmp/fork" fetch -q upstream
[[ $(sync plan) == *"1 pending upstream change(s), 1 flagged"*"FORK-OWNED: fork.txt"* ]] ||
  fail "the next plan has only the new change, flagged as fork-owned" "$(sync plan)"
set +e
out=$(sync merge)
code=$?
set -e
((code == 3)) || fail "a conflicted merge exits 3" "$out"
[[ $out == *"fork.txt   (fork-owned: the fork wins)"* ]] || fail "the conflict names the fork-owned path" "$out"
git -C "$tmp/fork" checkout -q --ours fork.txt
git -C "$tmp/fork" add fork.txt
git -C "$tmp/fork" commit -q --no-edit
[[ $(cat "$tmp/fork/fork.txt") == mine ]] || fail "the fork's version is kept"
report=$(sync finish)
grep -q "fork.txt\` (fork-owned: the fork's version kept)" "$report" || fail "the report lists the resolved conflict" "$(cat "$report")"
pass "a later sync takes only new changes and keeps the fork's side of a conflict"

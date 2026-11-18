# Upstream sync

Read this before syncing this fork with upstream Omarchy, by hand or as the scheduled
`upstream sync` agent (`.github/workflows/upstream-sync.yml`).

This fork diverges on purpose and keeps up on purpose. Each sync brings upstream's new
features and improvements in, leaves out what this fork has decided against, and keeps
every change this fork made. A person reviews and merges the result. You prepare one pull
request; you never merge it, push to `main`, or force-push.

## The model

- **Merge, then diverge.** Upstream (`default/upstream.toml`: `omacom/omarchy`, `quattro`)
  is merged into a sync branch, so git keeps it as an ancestor and the next sync only sees
  what is new. An upstream change this fork leaves out is merged and then reverted on that
  branch (`bin/upstream-sync decline`), with its reason recorded in `.upstream/ledger.tsv`.
- **Source stays in upstream's naming.** `bin/rebrand` applies `default/brand.toml` to builds,
  not to the tree, so a conflict means this fork really changed that code. Never run
  `bin/rebrand --apply` on a sync branch.
- **`bin/upstream-sync` is mechanical; the calls are yours.** It lists, merges, reverts,
  checks and records. It does not decide what is worth taking or how a conflict comes out.

## The procedure

1. `bin/upstream-sync status`. If nothing is pending, stop: write "nothing pending" to the
   result file and open no pull request.
2. `bin/upstream-sync plan`, then read every flagged change with `git show <sha>` and enough
   of the rest to judge it. `plan --json` gives the same data structured.
3. Decide each change (see **What to take** below). Note the declines and their reasons.
4. `bin/upstream-sync merge`. On exit 3, resolve every listed conflict (see **Conflicts**),
   `git add` each file, then `git commit --no-edit`.
5. `bin/upstream-sync decline <sha> -r "<reason>"` for each change you leave out. The reason is
   for the reviewer: one sentence, specific. If a revert conflicts, resolve it and
   `git revert --continue`.
6. `bin/upstream-sync check`. Fix any failure the merge caused, in small commits named
   `Sync: <what you fixed>`. Run the focused suites for areas upstream touched heavily
   (`./test/cli`, `./test/shell`, `./test/all` where their tools are installed) and say in
   the pull request what you ran and what you could not.
7. `bin/upstream-sync finish`. It records every decision in the ledger, commits it, and prints
   the path of the report.
8. Push the branch and open **one** pull request against `main`:
   `gh pr create --base main --title "Upstream sync: <n> changes to <branch>@<short>" --body-file <report>`,
   then add a short **Notes** section at the top of the body: anything risky, anything you
   adapted rather than took as-is, anything the reviewer should test by hand. Write the pull
   request's URL to the result file.

## What to take

Take upstream's **features, improvements, fixes, security and performance work**: that is
the point of following upstream. Take the dependency and packaging changes they need too.

Decline a change when it:

- **reverses a divergence this fork made**: removes or rewrites something this fork changed
  on purpose (look at `git log --first-parent main` for the fork's own commits);
- **touches a fork-owned path** (`fork_owned` in `default/upstream.toml`) in a way that fights
  the fork's version. Port the useful part onto the fork's version instead of declining
  outright, when there is one;
- **matches a `decline` rule** in `default/upstream.toml`, unless you can say why this
  instance is different;
- **is upstream's own promotion or identity** with nothing technical in it (release notes,
  announcement banners, Omarchy-only links that `[preserve]` does not already cover).

When in doubt, **take** the change and say why in the Notes. A declined improvement is harder
to notice than a taken one.

## Conflicts

- **A fork-owned path:** the fork's version wins. Then port upstream's *intent* onto it if
  that intent still applies (a renamed variable, a fixed bug), and mention it in the Notes.
- **Elsewhere:** combine both sides. Keep the fork's behaviour, and keep upstream's fix or
  feature. If the two can't coexist, keep the fork's behaviour and decline the upstream change
  with the reason.
- Never resolve a conflict by deleting the fork's work to make the merge clean.
- `bin/upstream-sync check` fails on any conflict marker left in a tracked file.

## Policy changes

The policy is `default/upstream.toml` and is fork-owned. When a sync shows a pattern worth a
rule (the same kind of change declined three times, say), propose the rule in the pull
request's Notes. Don't add it in the same sync: the reviewer decides policy.

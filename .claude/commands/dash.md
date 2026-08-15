---
description: Generate a labeled, self-healing tmux monitoring dashboard for this machine
argument-hint: panes/services to include (optional — default system/health/journal)
bashos:
  loop: refine
  requires-args: false
---
Generate a tmux monitoring-dashboard script for this machine, following the
forge-dash pattern (docs/FORGE.md). Requested panes: $ARGUMENTS (if empty:
a system monitor, a `bin/os-health` watch, and a log tail).

Requirements — each exists because its absence broke a real dashboard:

- One idempotent bash script, `set -Eeuo pipefail`, shellcheck-clean, that
  builds a `dash` window in a tmux session (create the session if missing).
- **Absolute paths for every pane command** — tmux panes spawn `sh` with a
  bare PATH; `watch my-script` dies with "not found" while your shell finds
  it fine.
- `tmux set-option -g window-size latest` — otherwise windows latch to a
  stale client geometry and full-screen tools refuse to draw ("terminal too
  small") even though the live client is huge.
- Labeled sections: `pane-border-status top` + a title per pane
  (`select-pane -T`), so every section names itself on the monitor.
- A `--heal` mode that respawns dead panes and rebuilds missing windows but
  **never steals focus and prints nothing** — it will run from cron.
- Root-only readings (journals, firewalls) must be probed via `sudo -n` —
  a pane running as an unprivileged user otherwise reports a false CRIT
  forever, and the check measures who asked instead of the machine.
- End with the cron line for the heal loop and the one-liner to attach.

Return the script in one fenced block, then a **PANES** table (pane → command
→ why), then the install steps.

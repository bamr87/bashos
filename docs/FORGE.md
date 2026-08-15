# The Forge Pattern — dev-server monitoring as bashOS userland

How a physical dev box ("forge", Debian 13 on the LAN) is provisioned and
watched, and how that process is folded into bashOS. The pattern predates the
repo: it was built by hand on real hardware, broke in instructive ways, and
each rule below is the scar tissue. bashOS adopts the *process*; the box keeps
its own scripts (`~/setup/*.sh` on the machine, mirrored conceptually here).

## The concept

1. **A deterministic verdict floor.** One read-only script emits
   `[ OK ]/[WARN]/[CRIT] check detail` lines with real numbers and exits
   nonzero on any non-OK. Judgment (a model, a human) layers *on top* of the
   floor and may never contradict it — the same "deterministic floor first"
   idiom the quest-fix and idea-intake lanes use elsewhere.
   In bashOS: `bin/os-health` (portable macOS/Linux), consumed by `/health`.
2. **A labeled, self-healing dashboard.** A tmux `dash` window with titled
   panes (system / health / stack / journal), rebuilt idempotently by one
   script with a `--heal` mode cron runs every 10 minutes.
   In bashOS: `/dash` generates that script for any machine.
3. **The console mirror.** The box's physical monitor boots into the shared
   tmux session; every SSH login joins it. One terminal, many windows.
4. **Remote = local + ssh.** bashOS loops stay network-free by policy. To
   drive a server, run bashOS *on* the server:
   `ssh forge 'NOTMUX=1 bashos run "/health"'` — the react loop probes
   localhost there, and the terminal here just carries text.

## Hard-won rules (each one broke for real first)

| Rule | What happened without it |
|---|---|
| Absolute paths in tmux pane commands | Panes spawn `sh` with a bare PATH; `watch forge-health` died with `not found` while interactive shells found it fine. Fix: symlink tools into `/usr/local/bin` and invoke absolutely. |
| `tmux set-option -g window-size latest` | The dash window latched to a stale 327×40 client that had long disconnected; btop refused to draw ("terminal too small") on a 150×119 monitor. |
| Root-only checks probe via `sudo -n` | The firewall check ran fine by hand and reported `[CRIT] ufw INACTIVE` forever on the dashboard — it was measuring who asked, not the firewall. |
| `--heal` never steals focus, never prints | A cron heal that ends with `select-window` yanks the console to the dashboard every 10 minutes, whatever you were doing. |
| Subnet broadcast for WoL | The LAN is a /22; magic packets to `192.168.4.255` went nowhere. Broadcast to the real subnet broadcast (`192.168.7.255`) first, then global. |
| Check the journal before blaming software | A mid-session outage read like a crash or suspend; the journal said `Power key pressed short` — someone bumped the button. Verdicts need evidence. |

## What lives where

| Piece | Location | Role |
|---|---|---|
| `bin/os-health` | this repo | portable verdict floor (macOS + Linux) |
| `/health` | `.claude/commands/health.md` | react loop: floor first, then investigate non-OK lines |
| `/dash` | `.claude/commands/dash.md` | refine loop: generate the dashboard script for a machine |
| react probe allowlist | `src/bashos/loops/react.py` | `bin/os-health` + narrow read-only tmux verbs added; still no write/network tools |
| forge box scripts | `~/setup/` on the box | idempotent 01-system … 04-dashboard; `~/DEVBOX.md` is its runbook |

## The remote layer (`bashos remote`)

`src/bashos/remote.py` packages the pattern end to end, with Claude Code
OAuth as the default AI wiring. The division of labor is the security model:

```
 ┌ Mac / wherever bashOS runs ─────────────┐      ┌ dev box (forge) ─────────────┐
 │ bashos remote ask forge "…"             │      │                              │
 │   1. CODE runs one ssh round trip ──────┼─────▶│ health floor + fixed probes  │
 │   2. MODEL reasons over the readings    │      │ (read-only, marker-parsed)   │
 │      (Claude Code OAuth, local)         │      │                              │
 │   3. CODE mirrors the interaction ──────┼─────▶│ ~/monitoring/ai/session.log  │
 └─────────────────────────────────────────┘      │  → `ai` pane on the MONITOR  │
                                                  └──────────────────────────────┘
```

- **Code does the ssh, never the model.** The probe list is fixed in
  `remote.PROBES`; the model only ever sees gathered text. No loop gains a
  network tool — deny-by-default holds end to end.
- `bashos remote doctor <host>` — ssh, tmux console, monitor client, floor.
- `bashos remote health <host>` — stream `bin/os-health` over stdin, verdicts
  back; exit code = worst verdict.
- `bashos remote setup <host>` — user-level install (`~/.local/bin/
  bashos-health`, AI log, console `ai` window); root symlink only via
  `sudo -n`, skipped silently otherwise.
- `bashos remote ask <host> "question"` — the full loop above. `--dry-run`
  renders the prompt without a model call or mirror; `--no-mirror` keeps the
  interaction off the box's display.
- Hosts are plain `~/.ssh/config` aliases — no host registry to maintain.

**How an interaction reaches the monitor** — three surfaces, because a tail
pane alone is easy to miss next to btop's animation:

1. a transient `display-popup` overlay (96%×75%) on whichever client sits on
   the console — the physical monitor — dismissed by any key or 45s; the
   popup is backgrounded on the box so the ssh (and the CLI) returns
   immediately;
2. the dash window's `ai` pane (35 rows) tails the running history;
3. the full-screen `ai` window keeps the long transcript.

Windows are never switched and focus is never stolen — the popup overlays
and disappears. Boxes without a tmux console still get the log.

Validated live against forge 2026-08-14: doctor all-OK (monitor attached,
focused, 150×120), ask answered over real probes, the popup process
confirmed running against `/dev/tty1`, and the interaction persisted in the
dash `ai` pane.

### Hand-rolled vs packaged

The box keeps its richer, box-specific floor (`forge-health`: cpu-temp,
SMART, ufw, per-mount disks) and its own dashboard builder (`forge-dash`,
now 5 labeled panes: system / health / stack / journal / **ai**, plus a
full-screen `ai` window). bashOS ships the portable floor and the transport;
where a box-specific floor exists it stays authoritative on the box, and the
bashOS floor travels over stdin so remote verdicts never depend on what is
installed.

## Non-goals

- No ssh/network tools in any *loop's* allowlist — remote is the `remote`
  module's code path, driven from the CLI, not model capability creep.
- bashOS does not manage the box's service stack (Postgres/Redis/Adminer/
  Portainer under `~/dev/stack/`); `/health` and `remote ask` only *read*
  container state where a docker CLI exists.

# Remote sessions: drive a machine and run Claude Code on it

> How to watch and control another machine's desktop and run recorded Claude Code sessions on it from your Mac with `scripts/oneos-remote`, over SSH, with VNC left for people to look on.

Once a machine is installed and on the network, one-os can keep working on it without anyone at its keyboard. `oneos-remote` is the tool: it installs a small agent on the machine, then takes screenshots, sends keyboard and mouse input, starts Claude Code sessions there, and keeps a record of who connected and what was on screen.

It needs SSH key access to the machine and nothing else. It never uses the VNC password.

## Why not just VNC

VNC is how a person looks at the machine. It is a poor way for a program to drive it:

| | Through a VNC client | `oneos-remote` (SSH + agent) |
| --- | --- | --- |
| Typing | Depends on the client; synthetic keystrokes were lost about 1 in 10 in testing | Injected into the kernel input layer (`/dev/uinput`): 890 of 890 characters arrived |
| Pointer | Accurate on the server (a click landed within 2 px), but the client decides what you see | Absolute, pixel-accurate, independent of display scaling |
| Screen | Needs the viewer window in front | A screenshot in about 0.4 s, from any terminal |
| Password | The VNC password | None: your SSH key |
| Claude Code | Click and type into VS Code | A terminal session you send text to and read back, or one headless prompt |

## Set up

```bash
echo 'deck@192.168.4.136' > ~/.config/one-os/remote-host   # or: export ONEOS_REMOTE=…, or -H user@host
scripts/oneos-remote install
scripts/oneos-remote status
```

`install` copies `remote/agent/` to `~/.local/share/oneos-remote/bin` on the machine and starts two user services: `oneos-input` (a virtual keyboard and pointer) and `oneos-monitor` (the log and the screen recorder). It warns if `tmux`, `spectacle`, `ffmpeg` or write access to `/dev/uinput` is missing. `uninstall` removes the agent and keeps the recordings.

The machine needs a KDE Plasma (Wayland) desktop session for screenshots; SteamOS in Desktop Mode qualifies, Gaming Mode does not. Claude Code sessions and headless prompts work without a desktop.

## Look and act

```bash
scripts/oneos-remote shot                      # prints a local JPG path (scaled to 1700 px wide)
scripts/oneos-remote click 812 440             # pixels in the screenshot you just took
scripts/oneos-remote key ctrl+shift+p
scripts/oneos-remote type 'Claude Code: Open in New Tab'
scripts/oneos-remote key enter
```

Coordinates always refer to the last `shot`, scaled or not. The pointer and keyboard are the machine's real ones: anyone sitting at it, or watching over VNC, sees them move. Typing covers US-layout ASCII.

## Run Claude Code there

One prompt, answer on stdout (about 2 seconds for a short one):

```bash
scripts/oneos-remote claude run --cwd /home/deck/project "Summarise what changed in the last commit"
```

An interactive session you can come back to:

```bash
scripts/oneos-remote claude start fix-wifi --cwd /home/deck/project --prompt "Find why wlan0 is down"
scripts/oneos-remote claude wait fix-wifi       # until the screen stops changing
scripts/oneos-remote claude view fix-wifi       # what it shows now
scripts/oneos-remote claude send fix-wifi "Yes, apply that"
scripts/oneos-remote claude keys fix-wifi Escape
scripts/oneos-remote attach fix-wifi            # sit in it yourself; Ctrl-b d to leave
scripts/oneos-remote claude stop fix-wifi
```

Sessions run in tmux under the user's service manager, so they survive the SSH connection that started them. The Claude binary is the one on `PATH`, or the one the VS Code extension ships; set `ONEOS_CLAUDE_BIN` on the machine to pick another. The first session in a folder asks whether you trust it: answer it like any other prompt (`claude keys NAME Down Enter`), and only for folders you know.

## What is recorded

Everything is on the machine, under `~/.local/state/oneos-remote/`:

| What | Where | Notes |
| --- | --- | --- |
| Connections and sessions | `events.jsonl` | VNC and SSH clients connecting and leaving (by address), Claude sessions starting and stopping, recordings saved |
| Interactive Claude sessions | `claude/NAME-DATE/` | `meta.json`, plus `term.log` and `term.timing`: replay with `scriptreplay` |
| Headless prompts | `claude/run-DATE/` | `meta.json` and the full event stream, `stream.jsonl` |
| The screen | `screen/YYYY-MM-DD/screen-HHMMSS.mp4` | One frame a second while a VNC client is connected, in 5-minute files; about 0.5 MB a minute at 3440x1440 |

```bash
scripts/oneos-remote events 50
scripts/oneos-remote claude log fix-wifi
scripts/oneos-remote record list
scripts/oneos-remote record pull               # copies the MP4s to build/remote/recordings/
scripts/oneos-remote record on                 # record even with no VNC client; `record off` to stop
```

Screen recordings older than 14 days are deleted (`ONEOS_KEEP_DAYS` in the service's environment changes that). The log and the Claude session folders are kept until you remove them.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| A Claude session ends the moment it starts | The tmux server was started inside an SSH login and was killed with it | Start sessions with `oneos-remote claude start`, which uses `systemd-run --user`; do not start `tmux -L oneos` by hand over SSH |
| `screenshot failed` | No Plasma desktop session (Gaming Mode, or logged out) | Switch to Desktop Mode; Claude sessions still work |
| `key`, `type` or `click` do nothing | `/dev/uinput` is not writable by your user | `install` warns about this; on SteamOS the `deck` user has access |
| The pointer jumps while you use VNC | Something is driving the machine with `oneos-remote move` or `click` | It is the same pointer: stop the other driver |
| The VNC pointer looks offset from where clicks land | The viewer draws its own cursor; with fractional display scaling (115 % here) it can sit beside the real one | Clicks still land correctly; set the display to 100 % if it bothers you |

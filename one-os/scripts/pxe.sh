#!/usr/bin/env bash
# pxe.sh — run netboot/server.py (HTTP + ProxyDHCP + TFTP) as a background service on this machine.
#
#   scripts/pxe.sh start [IFACE]   start in the background (IFACE: default = the default route's)
#   scripts/pxe.sh stop            stop it (check status first: a PC mid-download would lose it)
#   scripts/pxe.sh restart [IFACE]
#   scripts/pxe.sh status          running?, address, menu URL, active PCs, recent events
#   scripts/pxe.sh logs [-f]       the event log (build/netboot/server.log)
#   scripts/pxe.sh ssh-key [KEY.pub]  let network-booted PCs accept SSH from this public key
#   scripts/pxe.sh agent-install   macOS: start at login and restart if it dies (LaunchAgent)
#   scripts/pxe.sh agent-remove
#
# Make targets wrap these: make pxe-start / pxe-stop / pxe-restart / pxe-status / pxe-logs.
# Runs as your user (macOS lets normal users bind ports 67/69); never touches the LAN's DHCP.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NB="$ROOT/build/netboot"
PIDF="$NB/server.pid"
OUT="$NB/server.out"
PORT="${PXE_PORT:-8780}"
LABEL="local.one-os.pxe"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3)"

running() { [[ -f $PIDF ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }
others() { pgrep -f "netboot/server.py" | grep -vx "$(cat "$PIDF" 2>/dev/null || echo none)" || true; }

start() {
  local iface="${1:-${IFACE:-}}"
  if running; then echo "already running (pid $(cat "$PIDF")); use restart"; return 0; fi
  if [[ -n $(others) ]]; then
    echo "another netboot/server.py is running (pid $(others | tr '\n' ' ')) — stop it first (kill it, or agent-remove)" >&2
    return 1
  fi
  mkdir -p "$NB"
  [[ -f $NB/live/filesystem.squashfs ]] || echo "note: build/netboot/live/ is empty — run 'make netboot' first" >&2
  cd "$ROOT"
  nohup "$PY" netboot/server.py --pxe --port "$PORT" ${iface:+--iface "$iface"} >>"$OUT" 2>&1 &
  echo $! >"$PIDF"
  for _ in $(seq 20); do
    curl -fs -m 1 "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1 && { status; return 0; }
    running || break
    sleep 0.25
  done
  echo "server did not come up; last output:" >&2; tail -5 "$OUT" >&2; rm -f "$PIDF"; return 1
}

stop() {
  if running; then kill "$(cat "$PIDF")"; sleep 1; echo "stopped (pid $(cat "$PIDF"))"; rm -f "$PIDF"
  else echo "not running"; rm -f "$PIDF"; fi
  [[ -z $(others) ]] || echo "note: other server.py processes still running: $(others | tr '\n' ' ')"
}

status() {
  local j
  if ! j="$(curl -fs -m 2 "http://127.0.0.1:$PORT/api/status" 2>/dev/null)"; then
    echo "not running on :$PORT"; return 1
  fi
  python3 - "$j" <<'EOF'
import json, sys, time
d = json.loads(sys.argv[1]); s = d.get("server") or d.get("state") or {}
ip, iface = s.get("server_ip"), s.get("iface")
print(f"running · PXE {'on ' + str(iface) if s.get('pxe') else 'off'} · {ip}:{s.get('http_port')} · menu http://{ip}:{s.get('http_port')}/boot.ipxe")
now = time.time()
for c, v in sorted((d.get("clients") or {}).items(), key=lambda kv: -kv[1].get("last", 0))[:8]:
    age = int(now - v.get("last", now))
    print(f"  {c:17} {age:>6}s ago  {v.get('last_kind', ''):6} {v.get('last_msg', '')[:90]}")
EOF
}

case "${1:-status}" in
  start) shift; start "$@" ;;
  stop) stop ;;
  restart) shift; stop; start "$@" ;;
  status) status ;;
  logs) shift; if [[ ${1:-} == -f ]]; then tail -n 40 -F "$NB/server.log"; else tail -n 60 "$NB/server.log"; fi ;;
  ssh-key)
    # Network-booted PCs accept SSH from these keys (keys only). Public keys only, ever.
    key="${2:-$HOME/.ssh/id_ed25519.pub}"
    [[ $key == *.pub && -f $key ]] || { echo "need a public key file (*.pub): $key" >&2; exit 1; }
    grep -qE '^(ssh-|ecdsa-|sk-)' "$key" || { echo "$key doesn't look like an SSH public key" >&2; exit 1; }
    mkdir -p "$NB"; cat "$key" >>"$NB/authorized_keys"; sort -u -o "$NB/authorized_keys" "$NB/authorized_keys"
    echo "network-booted PCs will accept: $(awk '{print $1, $3}' "$NB/authorized_keys" | paste -sd ',' -)"
    echo "(remove: rm build/netboot/authorized_keys)" ;;
  agent-install)
    [[ $(uname) == Darwin ]] || { echo "LaunchAgents are macOS only (on Linux: a systemd user unit)"; exit 1; }
    mkdir -p "$(dirname "$PLIST")" "$NB"
    cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>$ROOT/netboot/server.py</string><string>--pxe</string><string>--port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$OUT</string>
  <key>StandardErrorPath</key><string>$OUT</string>
</dict></plist>
EOF
    running && stop
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "installed $PLIST (starts at login, restarted if it exits)"; sleep 2; status ;;
  agent-remove)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"; echo "removed $LABEL" ;;
  -h|--help|help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "unknown command: $1 (see --help)" >&2; exit 2 ;;
esac

# shellcheck shell=bash
# Shared by the one-os remote agent scripts (they run on the remote machine).
ONEOS_STATE="${ONEOS_REMOTE_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/oneos-remote}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then
  for s in "$XDG_RUNTIME_DIR"/wayland-[0-9]; do [[ -S "$s" ]] && WAYLAND_DISPLAY="$(basename "$s")" && break; done
  export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
fi
mkdir -p "$ONEOS_STATE"

die() { echo "$(basename "$0"): $*" >&2; exit 1; }

# event KIND key=value …  → one JSON line in events.jsonl (values are strings).
event() {
  local kind="$1"; shift
  python3 - "$ONEOS_STATE/events.jsonl" "$kind" "$@" <<'PY'
import json, sys, time
path, kind, *pairs = sys.argv[1:]
rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": kind}
rec.update(p.split("=", 1) for p in pairs)
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\n")
PY
}

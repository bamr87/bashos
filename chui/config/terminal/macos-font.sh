#!/usr/bin/env bash
set -euo pipefail
FONT_NAME="${CHUI_FONT_NAME:-MesloLGS Nerd Font}"
FONT_SIZE="${CHUI_FONT_SIZE:-13}"

osascript <<EOF
tell application "Terminal"
  try
    set font name of default settings to "${FONT_NAME}"
    set font size of default settings to ${FONT_SIZE}
  end try
  try
    set font name of settings set "Clear Dark" to "${FONT_NAME}"
    set font size of settings set "Clear Dark" to ${FONT_SIZE}
  end try
  repeat with w in windows
    try
      set font name of current settings of w to "${FONT_NAME}"
      set font size of current settings of w to ${FONT_SIZE}
    end try
  end repeat
end tell
EOF

printf 'terminal font: %s %s\n' "$FONT_NAME" "$FONT_SIZE"

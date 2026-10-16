# Mac-style editing: Opt = word, Cmd = line.

WORDCHARS='*?[]~&;!#$%^(){}<>'

chui-bind() {
  emulate -L zsh
  local widget=$1 seq
  shift
  for seq in "$@"; do
    bindkey -M emacs "$seq" "$widget"
    bindkey -M viins "$seq" "$widget"
  done
}

# Cmd+Left/Right (also Home/End, Ctrl-A/E)
chui-bind beginning-of-line \
  '^A' '^[[H' '^[[1~' '^[OH' '^[[1;9D' '^[[1;8D' '^[[1;2H'
chui-bind end-of-line \
  '^E' '^[[F' '^[[4~' '^[OF' '^[[1;9C' '^[[1;8C' '^[[1;2F'

# Opt+Left/Right and Ctrl+Left/Right
chui-bind backward-word \
  '^[b' '^[^[[D' '^[OD' '^[[1;3D' '^[[1;5D' '^[[1;4D'
chui-bind forward-word \
  '^[f' '^[^[[C' '^[OC' '^[[1;3C' '^[[1;5C' '^[[1;4C'

# Deletes
bindkey -M emacs '^U' backward-kill-line
bindkey -M viins '^U' backward-kill-line
chui-bind backward-kill-word '^W' '^[^?' '^[^H' '^[[3;3~'
chui-bind kill-word '^[d' '^[[3;5~' '^[[3;9~'
chui-bind kill-line '^K'
chui-bind delete-char '^[[3~' '^[[3;2~'
chui-bind backward-delete-char '^?' '^H'

# Cmd+Up/Down = buffer, Opt+Up/Down = history search
chui-bind beginning-of-buffer-or-history '^[[1;9A' '^[[5~' '^[[1;5A'
chui-bind end-of-buffer-or-history '^[[1;9B' '^[[6~' '^[[1;5B'
chui-bind up-line-or-beginning-search '^[[A' '^[OA' '^[[1;3A'
chui-bind down-line-or-beginning-search '^[[B' '^[OB' '^[[1;3B'

chui-bind undo '^_' '^/'
chui-bind yank '^Y'

if (( ${+widgets[autosuggest-accept]} )); then
  bindkey -M emacs '^ ' autosuggest-accept
  bindkey -M viins '^ ' autosuggest-accept
fi

unfunction chui-bind

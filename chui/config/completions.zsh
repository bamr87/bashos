zstyle ':completion:*' menu no
zstyle ':completion:*' verbose yes
zstyle ':completion:*' extra-verbose yes
zstyle ':completion:*' group-name ''
zstyle ':completion:*' list-grouped true
zstyle ':completion:*' list-separator '—'
zstyle ':completion:*:descriptions' format '[%d]'
zstyle ':completion:*:messages' format '%d'
zstyle ':completion:*:warnings' format 'no matches: %d'
zstyle ':completion:*' matcher-list 'm:{[:lower:][:upper:]}={[:upper:][:lower:]}' 'r:|[._-]=* r:|=*'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"

zstyle ':fzf-tab:*' prefix ''
zstyle ':fzf-tab:*' switch-group '<' '>'
zstyle ':fzf-tab:*' fzf-min-height 12
zstyle ':fzf-tab:*' fzf-pad 4
zstyle ':fzf-tab:*' fzf-flags --height=45% --layout=reverse --border --cycle --info=inline --ansi \
  --bind=tab:down,btab:up,ctrl-j:down,ctrl-k:up,ctrl-n:down,ctrl-p:up,enter:accept,ctrl-space:toggle
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza -1 --icons=auto --group-directories-first --color=always $realpath 2>/dev/null'
zstyle ':fzf-tab:complete:z:*' fzf-preview 'eza -1 --icons=auto --group-directories-first --color=always $realpath 2>/dev/null'
zstyle ':fzf-tab:complete:proj:*' fzf-preview 'eza -1 --icons=auto --group-directories-first --color=always $realpath 2>/dev/null'
zstyle ':fzf-tab:complete:ls:*' fzf-preview 'eza -lah --icons=auto --color=always $realpath 2>/dev/null'
zstyle ':fzf-tab:complete:eza:*' fzf-preview 'eza -lah --icons=auto --color=always $realpath 2>/dev/null'
zstyle ':fzf-tab:complete:bat:*' fzf-preview 'bat --color=always --style=plain --line-range=:80 $realpath 2>/dev/null'
zstyle ':fzf-tab:complete:kill:argument-rest' fzf-preview 'ps -p $word -o pid,user,comm,args 2>/dev/null'
zstyle ':fzf-tab:complete:systemctl-*:*' fzf-preview 'systemctl status $word 2>/dev/null | head -20'

_chui() {
  local -a cmds
  cmds=(
    'menu:interactive TUI'
    'update:git pull + reinstall'
    'configure:icons, splash, font, theme'
    'dash:status box'
    'home:map $HOME + next level'
    'keys:keyboard shortcuts'
    'doctor:font / icons / tools'
    'check:verify install'
    'backup:snapshot configs'
    'restore:roll back last snapshot'
    'help:this list'
  )
  _describe -t commands 'chui' cmds
}
compdef _chui chui

_proj() {
  _files -W "$HOME/github" -/
}
compdef _proj proj

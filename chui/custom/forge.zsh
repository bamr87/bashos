# forge.zsh — manage, monitor, and connect to the forge dev box from the Mac.
# Auto-loaded by oh-my-zsh ($ZSH_CUSTOM). Everything hangs off one command:
#
#   forge                    join the console tmux session (what the monitor shows)
#   forge shell              private zsh on forge, outside tmux
#   forge wake | status      power it on (WoL) / reachability + health verdict
#   forge ps                 visual container status (forge-stack-report)
#   forge sh [name]          shell INTO a container (menu if no name)
#   forge logs [name] [N]    follow a container's logs, last N lines (menu if no name)
#   forge restart <name>     restart a container
#   forge stacks             compose projects on the box
#   forge compose <proj> ..  docker compose in ~/dev/<proj>  (e.g. forge compose elk ps)
#   forge health | journal   forge-health checks / journal report
#   forge net                listening ports, connections, 6 h traffic
#   forge top                btop over ssh
#   forge es <path>          (ELK stopped — unused)
#   forge sync [dir]         rsync a repo (default: cwd) to forge:dev/<name>
#   forge ci [run|list|…]    invoke GitHub workflows on forge via act (forge-ci)
#   forge ui <app>           open grafana|portainer|adminer|site|glances in the browser
#   forge help               this list

_forge_pick_container() {           # sets $REPLY to a running container name
  local -a names
  names=("${(@f)$(command ssh forge "docker ps --format '{{.Names}}' #nomirror")}") || return 1
  (( ${#names} )) || { echo "no running containers" >&2; return 1 }
  (( ${#names} == 1 )) && { REPLY=$names[1]; return 0 }
  local c; PS3="container> "
  select c in $names; do [[ -n $c ]] && { REPLY=$c; return 0 }; done
  return 1
}

forge() {
  local cmd=$1; (( $# )) && shift
  case $cmd in
    ""|console) command ssh forge ;;
    shell)      command ssh -t forge NOTMUX=1 zsh ;;
    wake)       wake-forge ;;
    status)
      if command ssh -o ConnectTimeout=3 forge true 2>/dev/null; then
        echo "forge: up"; command ssh forge "forge-health #nomirror" | head -4
        command ssh forge "docker ps --format '{{.Names}}' | wc -l #nomirror" | xargs echo "containers running:"
      else
        echo "forge: unreachable — try: forge wake"
      fi ;;
    ps)         command ssh forge "forge-stack-report #nomirror" ;;
    sh)
      local name=${1:-}
      [[ -z $name ]] && { _forge_pick_container || return 1; name=$REPLY }
      command ssh -t forge "docker exec -it $name sh -c 'command -v bash >/dev/null && exec bash || exec sh' #nomirror" ;;
    logs)
      local name=${1:-} tail=${2:-100}
      [[ -z $name ]] && { _forge_pick_container || return 1; name=$REPLY }
      command ssh -t forge "docker logs -f --tail $tail $name #nomirror" ;;
    restart)
      [[ -z $1 ]] && { echo "usage: forge restart <container>" >&2; return 1 }
      command ssh forge "docker restart $1" ;;
    stacks)     command ssh forge "docker compose ls #nomirror" ;;
    compose)
      local proj=$1; shift || true
      [[ -z $proj ]] && { echo "usage: forge compose <project> <args...>  (projects: forge stacks)" >&2; return 1 }
      command ssh -t forge "cd ~/dev/$proj && docker compose $* #nomirror" ;;
    health)     command ssh forge "forge-health #nomirror" ;;
    journal)    command ssh forge "forge-journal-report #nomirror" ;;
    net)
      command ssh forge "echo '── listening:'; ss -tlnp 2>/dev/null | tail -n +2 | awk '{print \$4}'
        echo '── established:'; ss -tn state established | tail -n +2 | awk '{print \$4, \"<-\", \$5}'
        echo '── traffic (today):'; vnstat --oneline 2>/dev/null | cut -d';' -f2-6 #nomirror" ;;
    top)        command ssh -t forge "btop #nomirror" ;;
    es)
      [[ -z $1 ]] && { echo "usage: forge es </index/_search?...> " >&2; return 1 }
      local out
      out=$(command ssh forge "curl -s 'http://127.0.0.1:9200$1' #nomirror")
      print -r -- "$out" | python3 -m json.tool 2>/dev/null || print -r -- "$out" ;;
    sync)
      local src=${1:-$PWD}; src=${src:A}
      local name=${src:t}
      [[ -d $src ]] || { echo "not a directory: $src" >&2; return 1 }
      echo "rsync $src → forge:dev/$name/"
      rsync -a --info=progress2 --exclude node_modules --exclude _site --exclude .jekyll-cache \
        --exclude __pycache__ --exclude .venv --exclude .next --exclude test-results \
        "$src/" "forge:dev/$name/" ;;
    ci)
      if (( $# == 0 )); then
        command ssh -t forge "forge-ci run ${PWD:t} #nomirror"
      else
        command ssh -t forge "forge-ci $* #nomirror"
      fi ;;
    ui)
      local -A urls=(
        grafana   "http://forge.local:3000"
        portainer "https://forge.local:9443"
        adminer   "http://forge.local:8080"
        site      "http://forge.local:4000"
        glances   "http://forge.local:61209"
      )
      [[ -n ${urls[$1]:-} ]] && open ${urls[$1]} || { echo "apps: ${(k)urls}" >&2; return 1 } ;;
    help|*)
      sed -n '4,20p' ${(%):-%x} | sed 's/^# \{0,3\}//' ;;
  esac
}

_forge() {
  local -a cmds apps
  cmds=(
    'console:join the console tmux session'
    'shell:private zsh on forge, outside tmux'
    'wake:power on (Wake-on-LAN)'
    'status:reachability + health'
    'ps:visual container status'
    'sh:shell into a container'
    'logs:follow container logs'
    'restart:restart a container'
    'stacks:compose projects on the box'
    'compose:docker compose in ~/dev/<proj>'
    'health:forge-health checks'
    'journal:journal report'
    'net:ports, connections, traffic'
    'top:btop over ssh'
    'es:elasticsearch query (unused)'
    'sync:rsync cwd to forge:dev/<name>'
    'ci:invoke GitHub workflows via act'
    'ui:open grafana/portainer/adminer/site/glances'
    'help:this list'
  )
  apps=(
    'grafana:dashboards :3000'
    'portainer:docker UI :9443'
    'adminer:database UI :8080'
    'site:jekyll :4000'
    'glances:system monitor :61209'
  )
  local state
  _arguments -C \
    '1:forge command:->cmds' \
    '*::arg:->args'
  case $state in
    cmds) _describe -t commands 'forge' cmds ;;
    args)
      case $words[1] in
        ui) _describe -t apps 'app' apps ;;
        sh|logs|restart)
          local cache="${XDG_CACHE_HOME:-$HOME/.cache}/chui/forge-ps"
          mkdir -p "${cache:h}"
          if [[ ! -s $cache ]] || (( $(date +%s) - $(stat -f %m "$cache" 2>/dev/null || echo 0) > 60 )); then
            command ssh -o ConnectTimeout=1 -o BatchMode=yes forge "docker ps --format '{{.Names}}' #nomirror" >|"$cache" 2>/dev/null || true
          fi
          [[ -s $cache ]] && compadd -X 'container' -- ${(f)"$(<$cache)"}
          ;;
        sync) _files -/ ;;
        compose) _files -W "$HOME/github" -/ ;;
      esac
      ;;
  esac
}

alias forge='noglob forge'
compdef _forge forge

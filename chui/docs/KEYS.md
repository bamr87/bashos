# Keyboard

> Every key chui sets up: Mac-style cursor, delete and edit keys in the shell, the Zellij bindings, and the home map.

Mac text-editing in the shell. **Restart Terminal.app** after install.

## Cursor

| Key | Action |
| --- | --- |
| **⌘ ←** | start of line |
| **⌘ →** | end of line |
| **⌥ ←** | previous word |
| **⌥ →** | next word |
| **⌃ ←** / **⌃ →** | previous / next word |
| **⌘ ↑** | top of history / buffer |
| **⌘ ↓** | bottom of buffer |
| **⌥ ↑** / **⌥ ↓** | history search (typed prefix) |
| **↑** / **↓** | history search (typed prefix) |

## Delete

| Key | Action |
| --- | --- |
| **⌘ ⌫** | delete to start of line |
| **⌘ ⌦** | delete to end of line |
| **⌥ ⌫** | delete previous word |
| **⌥ ⌦** | delete next word |
| **⌃ U** | delete to start of line |
| **⌃ K** | delete to end of line |
| **⌃ W** | delete previous word |

## Edit / search

| Key | Action |
| --- | --- |
| **⌃ Space** | accept autosuggestion |
| **⌃ R** | fuzzy history (fzf) |
| **⌃ T** | fuzzy files (fzf) |
| **⌥ C** | fuzzy cd (fzf) |
| **Tab** | fzf-tab menu (tips beside commands) |
| **↑ ↓** / **⌃ J K** | scroll completions |
| **enter** | accept completion |
| **⇧ Tab** | previous completion |
| **⌃ Space** | toggle multi-select (in tab menu) |
| **<** **>** | switch completion groups |
| **⌃ X ⌃ E** | edit command in `$EDITOR` |
| **⌃ Y** | yank (paste kill) |
| **⌃ /** | undo |
| **⌥ .** | insert last argument |

## Zellij (`zj`)

`chui configure` → Zellij keys picks one of two key sets.

**classic** (the default):

| Key | Action |
| --- | --- |
| **⌃ G** | lock / unlock |
| **⌃ P** | pane mode |
| **⌃ T** | tab mode |
| **⌃ N** | resize mode |
| **⌃ O** | session mode |
| **⌃ Q** | quit |

**unlock-first** (bashOS keys v1). Zellij starts locked, so every key reaches the app inside it:

| Key | Action |
| --- | --- |
| **⌃ G** | unlock (again, or **esc**: lock) |
| then **p** / **t** / **r** / **o** | pane / tab / resize / session mode |
| then **q** | quit |

In a mode, `h j k l` move or resize, `n` new, `x` close, `f` fullscreen; every action locks again.

## Home map (`hm` / `zh`)

Maximize first. Hidden entries are the ones Finder will not show.

| Key | Action |
| --- | --- |
| **`hm`** | map `~` + next level (two columns when the window is wide) |
| **`zh`** | zellij: visible \| hidden + stray pane |
| **`chui home sweep`** | pick strays, move to `~/Documents/Archive` |

`chui keys` prints this file.

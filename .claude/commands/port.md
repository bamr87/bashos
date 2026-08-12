---
description: Translate scripts between bash, POSIX sh, zsh, PowerShell, and Python
argument-hint: target language + the code
bashos:
  loop: prompt
---
Translate this between shells/languages:

$ARGUMENTS

- If the target isn't stated, infer it and say what you inferred. Supported directions include bash ↔ POSIX sh ↔ zsh ↔ PowerShell ↔ Python.
- Return the translated program in one fenced block, then a **DIFFERENCES** table: semantics that do not carry over 1:1 — word splitting, globbing, exit-status propagation, error handling, signals, quoting.
- Preserve behavior over style; where exact behavior is impossible, choose the closest equivalent and flag it.

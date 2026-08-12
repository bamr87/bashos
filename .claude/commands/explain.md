---
description: Explain a command, pipeline, error message, or config like an expert man page
argument-hint: command, snippet, or error text
bashos:
  loop: prompt
---
Explain the following like a man page written by a senior engineer:

$ARGUMENTS

Format:
- **NAME** — one line: what it is / does.
- **BREAKDOWN** — a table of the interesting tokens or flags and what each contributes.
- **BEHAVIOR** — what actually happens when it runs: exit codes, stdout vs stderr, side effects.
- **PITFALLS** — the 1–3 ways it bites people.
- **SAFER/BETTER** — a modern or safer alternative, if one exists.

Skip sections that don't apply. If the input is an error message, lead with the root cause instead of the format above.

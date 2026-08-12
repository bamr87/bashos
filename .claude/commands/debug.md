---
description: Diagnose a failing command or script from its error output (inspects this machine, read-only)
argument-hint: the command + error output, or a description of the failure
allowed-tools: Read, Glob, Grep, Bash(uname:*), Bash(which:*), Bash(ls:*), Bash(head:*), Bash(file:*), Bash(stat:*), Bash(env:*), Bash(git status:*), Bash(git log:*)
bashos:
  loop: react
---
Diagnose this failure:

$ARGUMENTS

You have read-only access to this machine (file reads plus a whitelist of
diagnostic commands). Investigate before you conclude:
- Verify your understanding: read the files, check versions, inspect the paths named in the error.
- Form ranked hypotheses; test the cheapest ones first.

Then report:
1. **ROOT CAUSE** — the most likely cause, with the evidence you found.
2. **FIX** — the exact command(s) or edit to make.
3. **VERIFY** — how to confirm it worked.

If the error alone is ambiguous and you cannot verify on this machine, say exactly what extra output you need.

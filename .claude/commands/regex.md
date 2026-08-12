---
description: Craft, explain, and test a regular expression
argument-hint: what the pattern should match
bashos:
  loop: prompt
---
Craft the regular expression for:

$ARGUMENTS

- Default flavor: POSIX ERE (`grep -E` / `sed -E`). Give the PCRE variant when they differ.
- Present: the pattern in a code fence, a piece-by-piece breakdown table, and a test table with 3+ matching and 3+ non-matching examples.
- State the failure modes: what it will wrongly match or miss, and when to stop using regex entirely (nested structures need a parser).
- End with a ready-to-run `grep -E '...'` (or sed/awk) invocation.

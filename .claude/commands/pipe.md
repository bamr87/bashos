---
description: Design a text/data-processing pipeline (grep/sed/awk/sort/jq)
argument-hint: the transformation you need
bashos:
  loop: prompt
---
Design a text-processing pipeline for:

$ARGUMENTS

- Show the final pipeline first, in one ```bash fence.
- Then a table mapping each stage → what it contributes.
- Prefer the boring classics (grep, sed, awk, sort, uniq, cut, tr, xargs) and jq for JSON — over clever single-tool tricks.
- Show a 3–5 line sample of input → output.
- Note the gotchas that apply here: field separators, locale (LC_ALL), buffering between pipe stages, GNU vs BSD flag differences.

---
description: Design a text/data-processing pipeline (grep/sed/awk/sort/jq)
argument-hint: the transformation you need
bashos:
  loop: prompt
---
Design a text-processing pipeline for:

$ARGUMENTS

- Show the final pipeline first, in one ```bash fence.
- Then a short table mapping each stage → what it contributes.
- Prefer the boring classics (grep, sed, awk, sort, uniq, cut, tr, xargs) and jq for JSON — over clever single-tool tricks.
- Show a 3–5 line sample of input → output.
- Note at most two gotchas that apply here (field separators, locale, buffering, GNU vs BSD).
- Keep the whole answer under ~40 lines. No essays, no extra variants unless asked.

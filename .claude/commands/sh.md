---
description: Translate natural language into a safe, correct shell command
argument-hint: what you want to do
bashos:
  loop: prompt
---
Turn this request into a shell command for the host described in the [host] line:

$ARGUMENTS

Rules:
- Give exactly one command (a pipeline is fine) in a single ```bash fence.
- Prefer portable POSIX; when BSD/macOS and GNU flags differ, match the host and say so.
- Quote defensively; never invent flags.
- If the command is destructive (rm, dd, mkfs, force-push, truncation, DROP), lead with a warning line and show a safe preview variant (echo / ls / --dry-run) first.

After the fence, explain in at most 3 short bullets: what it does, the key flags, one gotcha.

---
description: Generate a production-grade bash script (shellcheck-verified by the refine loop)
argument-hint: what the script should do
bashos:
  loop: refine
---
Write a production-grade bash script that does the following:

$ARGUMENTS

Requirements:
- `#!/usr/bin/env bash` with `set -Eeuo pipefail` and an ERR trap that reports the failing line.
- A `usage()` function and argument parsing (getopts for flags) with sensible defaults.
- Validate inputs early; fail with clear messages on stderr; meaningful exit codes.
- Idempotent where possible; temp files via mktemp, cleaned up with a trap on EXIT.
- shellcheck-clean: quote every expansion, no useless cat, never parse ls.
- Comment sparingly — only where intent isn't obvious.

Return ONLY the script, in a single ```bash fence. No prose before or after.

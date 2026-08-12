---
description: Security-review a shell script for injection, quoting, and privilege issues
argument-hint: paste the script
bashos:
  loop: prompt
---
Security-review this shell script:

$ARGUMENTS

Check systematically: unquoted expansions and word splitting; injection via
eval / source / `sh -c` / backticks fed untrusted input; unsafe temp files
(predictable names, missing mktemp); TOCTOU races; `curl | bash` and unverified
downloads; PATH and IFS trust; privilege use (sudo, setuid, chmod 777); secrets
in code, env, or history; destructive commands without guards.

Report findings ranked CRITICAL / HIGH / MEDIUM / LOW / INFO:
- each with the offending line, why it's exploitable (one-line attack sketch), and the fixed line.

Close with an overall verdict. Include a hardened rewrite only if the script is short (under ~30 lines). If nothing is wrong, say so plainly — do not invent findings.

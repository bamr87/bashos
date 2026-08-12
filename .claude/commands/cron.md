---
description: Build or explain cron expressions and schedules
argument-hint: schedule in english, or a cron expression
bashos:
  loop: prompt
---
Handle this scheduling request:

$ARGUMENTS

- Natural language → give the cron expression; a cron expression → explain it.
- Show the expression, a field-by-field table, and the next 3 run times (state the timezone you assumed).
- Warn about the classics when relevant: DST skips/doubles, `*/N` boundary behavior, missing PATH/env inside crontab, `%` escaping, day-of-month vs day-of-week OR logic.
- If the host is macOS or the job needs jitter/retries/logging, add the launchd or systemd-timer equivalent in 2 lines.

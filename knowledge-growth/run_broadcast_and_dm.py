"""Wrapper: run group broadcast + DM delivery in sequence.

OpenClaw cron captures stdout of this wrapper as the broadcast payload.
DM delivery runs silently (it already sends via API internally).
"""

import sys
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 1. Group broadcast — stdout goes to OpenClaw for delivery
result = subprocess.run(
    [sys.executable, "daily_broadcast.py"],
    capture_output=True, text=True, encoding="utf-8"
)
sys.stdout.write(result.stdout)
if result.stderr:
    sys.stderr.write(result.stderr)

# 2. DM delivery — silent, already sends via Slack API internally
subprocess.run(
    [sys.executable, "dm_deliver.py"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

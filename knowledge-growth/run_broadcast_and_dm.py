"""Wrapper: run group broadcast + DM delivery in sequence.

Self-contained: sends broadcast directly via Slack API instead of relying
on OpenClaw stdout capture (systemEvent jobs do not auto-capture stdout).
DM delivery is delegated to dm_deliver.py (already sends via API internally).
"""

import os
import sys
import subprocess
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _send_slack_message(channel: str, text: str) -> bool:
    token = os.getenv("SLACK_BOT_TOKEN") or os.getenv("SLACK_BOT_TOKEN_XOXB")
    if not token:
        print("[Broadcast] No SLACK_BOT_TOKEN found in environment", file=sys.stderr)
        return False
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"channel": channel, "text": text, "as_user": True},
            timeout=30,
        )
        data = r.json()
        if not data.get("ok", False):
            print(f"[Broadcast] Slack API error: {data.get('error', 'unknown')}", file=sys.stderr)
        return data.get("ok", False)
    except Exception as e:
        print(f"[Broadcast] Slack send failed: {e}", file=sys.stderr)
        return False


def main():
    os.chdir(r"C:\Hello-World\knowledge-growth")

    # 1. Generate broadcast content
    result = subprocess.run(
        [sys.executable, "daily_broadcast.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    broadcast_text = result.stdout.strip()

    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if not broadcast_text or "今日无更新" in broadcast_text:
        print("[Broadcast] No updates today, skipping delivery.")
    else:
        ok = _send_slack_message("C0AE7L7J0EL", broadcast_text)
        print(f"[Broadcast] {'✓' if ok else '✗'} C0AE7L7J0EL")

    # 2. DM delivery (silent — already sends via Slack API internally)
    dm_result = subprocess.run(
        [sys.executable, "dm_deliver.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if dm_result.stdout:
        for line in dm_result.stdout.strip().splitlines():
            print(f"[DM] {line}")
    if dm_result.stderr:
        print(dm_result.stderr, file=sys.stderr)


if __name__ == "__main__":
    main()

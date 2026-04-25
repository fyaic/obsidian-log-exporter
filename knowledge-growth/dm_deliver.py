"""DM Cross-Attention Delivery — send per-person DM via configured channels."""

import sys
import os
import json
import requests
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from scanner import scan_daily_increments
from daily_broadcast import build_dm_text


def send_slack_dm(channel: str, text: str, token: str) -> dict:
    """Send a DM via Slack chat.postMessage."""
    payload = json.dumps({"channel": channel, "text": text}, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers=headers,
        verify=False,
        timeout=30,
    )
    return resp.json()


def main():
    # 1. Scan
    results = scan_daily_increments(days=1)
    results = {k: v for k, v in results.items() if v}

    # 2. Load DM channel mapping
    # Supports flexible formats:
    #   {"Rosetta": "D0AH3RMFQQ1", "Veil": "D0AHK6X1N6L"}
    #   {"Rosetta": {"slack": "D0AH3RMFQQ1"}, "Veil": {"slack": "D0AHK6X1N6L"}}
    dm_raw = os.environ.get("DM_CHANNELS", "{}")
    try:
        dm_config = json.loads(dm_raw)
    except json.JSONDecodeError:
        print("Invalid DM_CHANNELS JSON, skipping DM delivery")
        return

    if not dm_config:
        print("DM_CHANNELS not configured, skipping DM delivery")
        return

    # 3. Slack token (optional — skip if not set)
    slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not slack_token:
        print("SLACK_BOT_TOKEN not set, skipping DM delivery")
        return

    # 4. Deliver per person
    for person, channel_info in dm_config.items():
        dm_text = build_dm_text(person, results)
        if not dm_text:
            print(f"No DM content for {person}, skipping")
            continue

        # Resolve channel ID
        slack_channel = None
        if isinstance(channel_info, str):
            slack_channel = channel_info
        elif isinstance(channel_info, dict):
            slack_channel = channel_info.get("slack")

        if not slack_channel:
            print(f"No Slack channel configured for {person}, skipping")
            continue

        result = send_slack_dm(slack_channel, dm_text, slack_token)
        if result.get("ok"):
            print(f"DM sent to {person} ({slack_channel})")
        else:
            print(f"Failed to DM {person}: {result.get('error')}")


if __name__ == "__main__":
    main()

"""Configuration for Knowledge Growth Daily Report."""

import os
from pathlib import Path

# --- Vault & Contributors ---
VAULT_PATH = Path(os.getenv("VAULT_PATH", r"C:\Users\ryshi\Documents\AIC-000"))

# Map Obsidian Sync device names to contributor display names.
# Format: {"device-name":"contributor", ...}
# Populated from .env DEVICE_MAP JSON string.
import json
_DEVICE_MAP_RAW = os.getenv("DEVICE_MAP", "")
DEVICE_MAP = {}
if _DEVICE_MAP_RAW:
    try:
        DEVICE_MAP = json.loads(_DEVICE_MAP_RAW)
    except json.JSONDecodeError:
        pass

# Normalize Sync usernames to preferred display names.
# Example: {"Rosetta Guo": "Rosetta", "veilchow": "Veil"}
_NAME_ALIAS_RAW = os.getenv("NAME_ALIAS", "")
NAME_ALIAS = {}
if _NAME_ALIAS_RAW:
    try:
        NAME_ALIAS = json.loads(_NAME_ALIAS_RAW)
    except json.JSONDecodeError:
        pass

# Default hardcoded aliases (can be overridden by .env)
NAME_ALIAS.setdefault("Rosetta Guo", "Rosetta")
NAME_ALIAS.setdefault("veilchow", "Veil")
NAME_ALIAS.setdefault("veil", "Veil")

# Folders to ignore during scanning
IGNORE_FOLDERS = {
    ".git",
    ".obsidian",
    ".trash",
    "Icebox",
    "Inbox",
    ".tmp",
    "node_modules",
    ".vscode",
}

# --- LLM Config ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# --- DM Delivery (optional) ---
# JSON mapping of contributor -> IM channel(s).
# Simple string (Slack channel ID): {"Rosetta": "D0AH3RMFQQ1", "Veil": "D0AHK6X1N6L"}
# Dict format (multi-channel, future-proof): {"Rosetta": {"slack": "D0AH3RMFQQ1"}, "Veil": {"slack": "D0AHK6X1N6L"}}
# If empty, dm_deliver.py skips DM delivery — no hard dependency on any IM platform.
_DM_CHANNELS_RAW = os.getenv("DM_CHANNELS", "")
DM_CHANNELS = {}
if _DM_CHANNELS_RAW:
    try:
        DM_CHANNELS = json.loads(_DM_CHANNELS_RAW)
    except json.JSONDecodeError:
        pass

# Default DM channels (can be overridden by env var above)
if not DM_CHANNELS:
    DM_CHANNELS = {
        "Rosetta": "D0AH3RMFQQ1",
        "Veil": "D0AHK6X1N6L",
    }

# --- Output ---
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "./reports"))

# If set, also write the daily report back into Obsidian vault at this relative path
# e.g. "T-B AI工作搭子/日报"
VAULT_REPORT_PATH = os.getenv("VAULT_REPORT_PATH", "")

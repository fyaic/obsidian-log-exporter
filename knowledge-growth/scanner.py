"""Scan Obsidian vault for daily increments and group by contributor."""

import os
import json
import time
import datetime
from pathlib import Path
from typing import List, Dict, Optional

from config import VAULT_PATH, IGNORE_FOLDERS

STATE_FILE = Path("state.json")
SYNC_HISTORY_FILES = [
    VAULT_PATH / ".obsidian" / "obsidian_log_export.json",
    VAULT_PATH / ".obsidian" / "sync_history_export.json",
]


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_scan": 0}


def save_state(last_scan: float):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_scan": last_scan}, f)


def load_sync_history() -> dict:
    """Load Obsidian Sync history export if available."""
    source_file = next((path for path in SYNC_HISTORY_FILES if path.exists()), None)
    if source_file is None:
        print("[Scan] No Obsidian Sync export found (expected after plugin runs).")
        return {}
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Build a map: relative_path -> latest sync metadata.
        sync_map = {}

        for entry in data.get("server_files", []):
            path = entry.get("path", "")
            if not path or entry.get("folder") or entry.get("deleted"):
                continue
            current = sync_map.get(path)
            mtime = entry.get("mtime", 0) or 0
            if current is None or mtime >= current.get("mtime", 0):
                sync_map[path] = {
                    "device": entry.get("device", ""),
                    "username": entry.get("username", ""),
                    "user": entry.get("user"),
                    "mtime": mtime,
                }

        for entry in data.get("sync_history", []):
            path = entry.get("path", "")
            versions = entry.get("versions", [])
            if versions:
                # Sort by ts desc, pick the latest.
                latest = sorted(versions, key=lambda v: v.get("ts", 0), reverse=True)[0]
                current = sync_map.get(path)
                latest_ts = latest.get("ts", 0) or 0
                if current is None or latest_ts >= current.get("mtime", 0):
                    sync_map[path] = {
                        "device": latest.get("device", ""),
                        "username": latest.get("username", "") or latest.get("email", ""),
                        "user": latest.get("user"),
                        "mtime": latest_ts,
                    }
        return sync_map
    except Exception as e:
        print(f"[Scan] Failed to load sync export: {e}")
        return {}


def read_file_with_fallback(file_path: Path) -> str:
    """Read file trying multiple encodings."""
    for encoding in ["utf-8", "utf-8-sig", "utf-16", "gbk", "latin-1"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeError, UnicodeDecodeError):
            continue
    return ""


def extract_frontmatter_author(content: str) -> str:
    """Extract author from YAML frontmatter if present."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if stripped.lower().startswith("author:"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


# Known team members — frontmatter authors outside this set are treated as external
# sources (e.g. web clippings, imported articles) and ignored for attribution.
_KNOWN_MEMBERS = {"Rosetta", "Veil"}


def guess_contributor(rel_path: str, content: str = "", sync_meta: Optional[dict] = None) -> str:
    """
    Determine contributor from authoritative sources only:
    1. frontmatter author (self-declared in file) — ONLY trusted for known team members
    2. Obsidian Sync username/device (edit log)

    No path-based guessing. If no authoritative source, returns "unknown".
    """
    from config import NAME_ALIAS

    # 1. Check frontmatter author — only trust if it resolves to a known team member
    if content:
        fm_author = extract_frontmatter_author(content)
        if fm_author:
            normalized = NAME_ALIAS.get(fm_author, fm_author)
            if normalized in _KNOWN_MEMBERS:
                return normalized
            # External author (e.g. web clipper import) — fall through to sync logs

    # 2. Check Obsidian Sync username/device mapping
    sync_meta = sync_meta or {}
    sync_username = str(sync_meta.get("username", "") or "")
    if sync_username:
        return NAME_ALIAS.get(sync_username, sync_username)

    sync_device = str(sync_meta.get("device", "") or "")
    if sync_device:
        from config import DEVICE_MAP
        for device_pattern, person in DEVICE_MAP.items():
            if device_pattern.lower() in sync_device.lower():
                return person
        # Device not in map — return raw device name so user can populate DEVICE_MAP
        return sync_device

    return "unknown"


def scan_daily_increments(vault_path: Path = VAULT_PATH, days: Optional[int] = None) -> Dict[str, List[Dict]]:
    """
    Scan vault for files modified since last scan (or last N days if days is set).
    Returns a dict: {contributor: [file_info, ...]}
    
    Note: When days is set (manual override), state is NOT updated so that
    the next incremental run still uses the original checkpoint.
    """
    now = time.time()
    state = load_state()
    manual_override = days is not None

    if manual_override:
        cutoff_time = now - (days * 86400)
        print(f"[Scan] Manual override: scanning last {days} day(s).")
    else:
        cutoff_time = state.get("last_scan", 0)
        if cutoff_time == 0:
            cutoff_time = now - 86400  # Default to last 24h if no state
            print("[Scan] No previous state, defaulting to last 24h.")
        else:
            last_str = datetime.datetime.fromtimestamp(cutoff_time).strftime("%Y-%m-%d %H:%M:%S")
            print(f"[Scan] Incremental scan since: {last_str}")

    results_by_contributor: Dict[str, List[Dict]] = {}
    sync_device_map = load_sync_history()

    for root, dirs, files in os.walk(vault_path):
        # Filter out ignored folders
        dirs[:] = [d for d in dirs if d not in IGNORE_FOLDERS and not d.startswith(".")]

        for file in files:
            if not file.endswith(".md"):
                continue

            file_path = Path(root) / file
            try:
                mtime = file_path.stat().st_mtime
            except OSError:
                continue

            if mtime < cutoff_time:
                continue

            rel_path = file_path.relative_to(vault_path).as_posix()
            content = read_file_with_fallback(file_path)
            sync_meta = sync_device_map.get(rel_path, {})
            contributor = guess_contributor(rel_path, content, sync_meta)

            # Skip empty or unreadable files
            if not content.strip():
                continue

            # Detect if file is newly created (ctime close to mtime)
            try:
                ctime = file_path.stat().st_ctime
                is_new = abs(mtime - ctime) < 60
            except OSError:
                is_new = False

            file_info = {
                "path": str(file_path),
                "rel_path": rel_path,
                "filename": file,
                "mtime": mtime,
                "mtime_str": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "contributor": contributor,
                "sync_device": sync_meta.get("device", ""),
                "sync_username": sync_meta.get("username", ""),
                "content": content,
                "is_new": is_new,
                # Extract first non-empty line as title hint
                "title_hint": _extract_title(content, file),
            }

            results_by_contributor.setdefault(contributor, []).append(file_info)

    # Sort each contributor's files by mtime desc
    for contributor in results_by_contributor:
        results_by_contributor[contributor].sort(key=lambda x: x["mtime"], reverse=True)

    # Save scan timestamp for next incremental run (skip on manual override)
    if not manual_override:
        save_state(now)
    else:
        print("[Scan] Manual override — state.json NOT updated.")

    return results_by_contributor


def _extract_title(content: str, fallback: str) -> str:
    """Extract title from markdown H1 or first non-empty line."""
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    for line in lines[:5]:
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("## "):
            return line[3:].strip()
    # Fallback to filename without extension
    return fallback[:-3] if fallback.endswith(".md") else fallback


if __name__ == "__main__":
    import json
    results = scan_daily_increments(days=7)
    print(json.dumps({k: len(v) for k, v in results.items()}, ensure_ascii=False, indent=2))

"""Write generated report back into Obsidian vault."""

from pathlib import Path
from config import VAULT_PATH


def write_to_vault(report_md: str, rel_path: str) -> Path:
    """Save report into the Obsidian vault at the specified relative path."""
    target = VAULT_PATH / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report_md, encoding="utf-8")
    return target

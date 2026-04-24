"""Knowledge Growth Daily Report — Main Entry."""

import argparse
import sys

# Fix Windows PowerShell GBK encoding crash on emoji/special chars
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

# Load .env before importing config
load_dotenv()

from scanner import scan_daily_increments
from reporter import generate_daily_report, save_report
from vault_writer import write_to_vault


def main():
    parser = argparse.ArgumentParser(description="Knowledge Growth Daily Report Generator")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Scan files modified in the last N days (overrides incremental state)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and print stats without calling LLM",
    )
    parser.add_argument(
        "--output",
        action="store_true",
        help="Save report to reports/ directory (default: True if not --dry-run)",
    )
    parser.add_argument(
        "--write-to-vault",
        type=str,
        metavar="REL_PATH",
        help="Also write report back into Obsidian vault at the given relative path (e.g. 'T-B AI工作搭子/日报')",
    )
    args = parser.parse_args()

    if args.days:
        print(f"[Scan] Scanning vault for last {args.days} day(s)...")
    else:
        print("[Scan] Running incremental scan since last run...")
    raw_results = scan_daily_increments(days=args.days)

    if not raw_results:
        print("[!] No modified files found in the specified period.")
        sys.exit(0)

    print("[OK] Found updates:")
    for contributor, files in sorted(raw_results.items()):
        print(f"     - {contributor}: {len(files)} file(s)")

    if args.dry_run:
        print("\n[STOP] Dry run mode — skipping LLM report generation.")
        sys.exit(0)

    print("\n[LLM] Generating report...")
    report_md = generate_daily_report(raw_results)

    if args.output or not args.dry_run:
        path = save_report(report_md)
        print(f"\n[Save] Report saved: {path}")

    if args.write_to_vault:
        vault_path = write_to_vault(report_md, args.write_to_vault)
        print(f"[Vault] Report written to: {vault_path}")

    # Also print to stdout for immediate viewing
    print("\n" + "=" * 60)
    print(report_md)
    print("=" * 60)


if __name__ == "__main__":
    main()

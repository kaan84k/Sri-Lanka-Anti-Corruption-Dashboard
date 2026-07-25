"""
Backfill / correct court_level in already-extracted data.
=========================================================
Recomputes each case's court level from the asterisk column position in the
source PDF (see resolve_court_levels in ciaboc_pipeline) and rewrites:

  * data/processed/ciaboc.db           — the cases table
  * data/processed/review/*.json       — rejected-row review files

Coordinates are authoritative. A case with no confidently-resolved asterisk
column is set to NULL (Unknown) rather than left on the LLM's wrong guess.

Run from project root:
    py -3 pipeline/backfill_court_levels.py           # apply
    py -3 pipeline/backfill_court_levels.py --dry-run  # preview only
"""

import os
import sys
import json
import glob
import sqlite3
from collections import Counter

from ciaboc_pipeline import resolve_court_levels, _norm_case_no

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "ciaboc.db")
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
REVIEW_DIR = os.path.join(PROJECT_ROOT, "data", "processed", "review")


def _map_for(pdf_name: str, cache: dict) -> dict:
    if pdf_name not in cache:
        path = os.path.join(RAW_DIR, pdf_name)
        cache[pdf_name] = resolve_court_levels(path) if os.path.exists(path) else {}
    return cache[pdf_name]


def fix_database(dry_run: bool) -> None:
    if not os.path.exists(DB_PATH):
        print(f"  no database at {DB_PATH}, skipping")
        return
    conn = sqlite3.connect(DB_PATH)
    cache: dict = {}
    before = Counter()
    after = Counter()
    changed = 0

    rows = conn.execute("SELECT id, case_no, court_level, source_pdf FROM cases").fetchall()
    for cid, case_no, old, pdf_name in rows:
        before[old] += 1
        new = _map_for(pdf_name, cache).get(_norm_case_no(case_no))  # None if unresolved
        after[new] += 1
        if new != old:
            changed += 1
            if not dry_run:
                conn.execute("UPDATE cases SET court_level = ? WHERE id = ?", (new, cid))

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"  cases: {len(rows)} | court_level changed on {changed}")
    print(f"    before: {dict(before)}")
    print(f"    after:  {dict(after)}")


def fix_review_files(dry_run: bool) -> None:
    cache: dict = {}
    for path in sorted(glob.glob(os.path.join(REVIEW_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        changed = 0
        for entry in entries:
            case = entry.get("case", {})
            new = _map_for(entry.get("source_pdf", ""), cache).get(
                _norm_case_no(case.get("case_no"))
            )
            if new != case.get("court_level"):
                case["court_level"] = new
                changed += 1
        if changed and not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
        print(f"  {os.path.basename(path)}: {len(entries)} rows | changed {changed}")


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    print(f"{'DRY RUN — no writes' if dry_run else 'APPLYING corrections'}\n")
    print("Database:")
    fix_database(dry_run)
    print("Review files:")
    fix_review_files(dry_run)
    print("\nDone.")


if __name__ == "__main__":
    main()

"""
Repair hearing dates that fell outside the week their source PDF covers.
=========================================================================
Gemini occasionally drifts the year while reading a column of dates: the week
26-30 Jan 2026 came back as 2026-01-26, 2027-01-27, 2028-01-28, 2029-01-29,
2030-01-30. The PDF filename (20260126_-_20260130.pdf) is ground truth, so any
row whose day and month land inside that window is moved back to the window's
year. Rows that do not match a day in the window are reported, never guessed at.

Usage:
    python fix_hearing_dates.py            # dry run: show what would change
    python fix_hearing_dates.py --apply    # write the fixes to the database
"""

import os
import sys
import json
import shutil
import sqlite3
from datetime import datetime

try:
    from .ciaboc_pipeline import DB_PATH, REVIEW_DIR, pdf_date_window, _window_days
except ImportError:
    from ciaboc_pipeline import DB_PATH, REVIEW_DIR, pdf_date_window, _window_days


def _corrected_date(hearing_date: str, pdf_name: str):
    """Date this row should carry, or None if it is already fine / unfixable."""
    window = pdf_date_window(pdf_name)
    if window is None:
        return None
    try:
        parsed = datetime.strptime(hearing_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    if window[0] <= parsed <= window[1]:
        return None
    for day in _window_days(window):
        if (day.month, day.day) == (parsed.month, parsed.day):
            return day.isoformat()
    return None


def fix_database(apply: bool, db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, case_no, hearing_date, source_pdf FROM cases ORDER BY id"
    ).fetchall()

    fixes, unfixable = [], []
    for case_id, case_no, hearing_date, source_pdf in rows:
        window = pdf_date_window(source_pdf)
        if window is None:
            continue
        parsed = datetime.strptime(hearing_date, "%Y-%m-%d").date()
        if window[0] <= parsed <= window[1]:
            continue
        corrected = _corrected_date(hearing_date, source_pdf)
        if corrected is None:
            unfixable.append((case_id, case_no, hearing_date, source_pdf))
        else:
            fixes.append((case_id, case_no, hearing_date, corrected, source_pdf))

    for case_id, case_no, old, new, pdf in fixes:
        print(f"  case {case_id:>5}  {case_no:<28} {old} -> {new}   ({pdf})")
    for case_id, case_no, bad, pdf in unfixable:
        print(f"  case {case_id:>5}  {case_no:<28} {bad} has no matching day in {pdf} — left alone")
    print(f"\n{len(fixes)} row(s) fixable, {len(unfixable)} need manual review")

    if not apply or not fixes:
        conn.close()
        return

    # UNIQUE (case_no, hearing_date): a corrected row can collide with a row
    # that already holds the right date. Report those instead of overwriting.
    collisions = []
    try:
        for case_id, case_no, _old, new, _pdf in fixes:
            existing = conn.execute(
                "SELECT id FROM cases WHERE case_no = ? AND hearing_date = ? AND id <> ?",
                (case_no, new, case_id),
            ).fetchone()
            if existing:
                collisions.append((case_id, case_no, new, existing[0]))
                continue
            conn.execute("UPDATE cases SET hearing_date = ? WHERE id = ?", (new, case_id))
        conn.commit()
    finally:
        conn.close()

    for case_id, case_no, new, other in collisions:
        print(f"  SKIPPED case {case_id} ({case_no} -> {new}): duplicate of case {other}")
    print(f"Applied {len(fixes) - len(collisions)} fix(es) to {db_path}")


def fix_review_files(apply: bool, review_dir: str = REVIEW_DIR) -> None:
    """Rejected rows carry the same bad dates — repair them too, so a human
    reviewing the file is not re-entering a wrong date by hand."""
    if not os.path.isdir(review_dir):
        return
    for name in sorted(os.listdir(review_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(review_dir, name)
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)

        changed = 0
        for entry in entries:
            case = entry.get("case") or {}
            hearing_date = case.get("hearing_date")
            source_pdf = entry.get("source_pdf") or ""
            if not hearing_date:
                continue
            corrected = _corrected_date(hearing_date, source_pdf)
            if corrected:
                print(f"  {name}: {case.get('case_no')} {hearing_date} -> {corrected}")
                case["hearing_date"] = corrected
                changed += 1

        if changed and apply:
            shutil.copyfile(path, path + ".bak")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
            print(f"  {name}: {changed} date(s) fixed (backup at {name}.bak)")


if __name__ == "__main__":
    apply_changes = "--apply" in sys.argv[1:]
    print("=== cases table ===")
    fix_database(apply_changes)
    print("\n=== review files ===")
    fix_review_files(apply_changes)
    if not apply_changes:
        print("\nDry run — nothing written. Re-run with --apply to save.")

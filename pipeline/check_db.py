"""
Quick sanity checks for the CIABOC database.
Run from project root:  py -3 pipeline\check_db.py
"""

import os
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "ciaboc.db")

conn = sqlite3.connect(DB_PATH)

print("=== Cases per hearing date (compare against the PDF) ===")
for date, count in conn.execute(
    "SELECT hearing_date, COUNT(*) FROM cases GROUP BY hearing_date ORDER BY hearing_date"
):
    print(f"  {date}: {count} cases")

print("\n=== Spot check: merged-text record (B.S. Priyadarshana) ===")
rows = conn.execute(
    "SELECT name, designation, institution FROM suspects WHERE name LIKE ?",
    ("%Priyadarshana%",),
).fetchall()
for r in rows:
    print(f"  name={r[0]!r}  designation={r[1]!r}  institution={r[2]!r}")
if not rows:
    print("  (not found - check how Gemini spelled the name)")

print("\n=== Suspects appearing on multiple dates ===")
for name, n in conn.execute("""
    SELECT s.name, COUNT(DISTINCT c.hearing_date) AS days
    FROM suspects s JOIN cases c ON s.case_id = c.id
    GROUP BY s.name HAVING days > 1
    ORDER BY days DESC LIMIT 10
"""):
    print(f"  {name}: appears on {n} dates")

print("\n=== Top institutions ===")
for inst, n in conn.execute("""
    SELECT institution, COUNT(*) FROM suspects
    WHERE institution IS NOT NULL
    GROUP BY institution ORDER BY 2 DESC LIMIT 10
"""):
    print(f"  {inst}: {n}")

print("\n=== 5 sample records ===")
for r in conn.execute("""
    SELECT c.hearing_date, c.case_no, c.court_level, s.name, s.designation
    FROM cases c JOIN suspects s ON s.case_id = c.id LIMIT 5
"""):
    print(f"  {r}")

conn.close()

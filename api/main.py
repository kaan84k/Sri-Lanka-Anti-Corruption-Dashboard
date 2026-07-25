"""
CIABOC Anti-Corruption Dashboard - API Backend
================================================
Read-only FastAPI service over data/processed/ciaboc.db

Run from project root:
    py -3 -m uvicorn api.main:app --reload --port 8000

Then open:
    http://127.0.0.1:8000/docs      <- interactive API documentation (free with FastAPI)

Requirements:
    pip install fastapi uvicorn
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from pipeline.identity_resolution import normalize_alias

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "ciaboc.db")

app = FastAPI(
    title="Sri Lanka Anti-Corruption Dashboard API",
    description="Read-only API over CIABOC court cause list data.",
    version="1.1.0",
)

# Allow the dashboard (any localhost port during development) to call this API.
# TIGHTEN allow_origins BEFORE DEPLOYING PUBLICLY, e.g. ["https://yourdashboard.lk"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    """Open a read-only connection per request. SQLite handles concurrent reads fine."""
    if not os.path.exists(DB_PATH):
        raise HTTPException(503, f"Database not found at {DB_PATH}. Run the pipeline first.")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    try:
        yield conn
    finally:
        conn.close()


def attach_children(conn, case_rows: list[sqlite3.Row]) -> list[dict]:
    """Given case rows, attach their file numbers and suspects in 2 queries (no N+1)."""
    cases = [dict(r) for r in case_rows]
    if not cases:
        return []
    ids = [c["id"] for c in cases]
    ph = ",".join("?" * len(ids))

    by_case_files: dict[int, list] = {i: [] for i in ids}
    for r in conn.execute(f"SELECT case_id, file_no FROM file_numbers WHERE case_id IN ({ph})", ids):
        by_case_files[r["case_id"]].append(r["file_no"])

    by_case_suspects: dict[int, list] = {i: [] for i in ids}
    for r in conn.execute(
        f"""SELECT s.case_id, s.person_id, s.name AS source_name,
                   COALESCE(p.canonical_name, s.name) AS name,
                   s.designation, s.institution
            FROM suspects s
            LEFT JOIN people p ON p.id = s.person_id
            WHERE s.case_id IN ({ph})""",
        ids,
    ):
        by_case_suspects[r["case_id"]].append(
            {
                "person_id": r["person_id"],
                "name": r["name"],
                "source_name": r["source_name"],
                "designation": r["designation"],
                "institution": r["institution"],
            }
        )

    for c in cases:
        c["file_nos"] = by_case_files[c["id"]]
        c["suspects"] = by_case_suspects[c["id"]]
    return cases


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"service": "CIABOC Dashboard API", "docs": "/docs"}


@app.get("/stats/summary")
def summary():
    """Headline numbers for the dashboard's top cards."""
    with get_db() as conn:
        return {
            "total_hearings": conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
            "unique_cases": conn.execute("SELECT COUNT(DISTINCT case_no) FROM cases").fetchone()[0],
            "total_suspect_records": conn.execute("SELECT COUNT(*) FROM suspects").fetchone()[0],
            "unique_suspects": conn.execute(
                """SELECT COUNT(DISTINCT
                           CASE
                               WHEN person_id IS NOT NULL THEN 'person:' || person_id
                               ELSE 'name:' || LOWER(name)
                           END)
                   FROM suspects"""
            ).fetchone()[0],
            "date_range": dict(
                conn.execute(
                    "SELECT MIN(hearing_date) AS from_date, MAX(hearing_date) AS to_date FROM cases"
                ).fetchone()
            ),
            "source_pdfs": conn.execute("SELECT COUNT(DISTINCT source_pdf) FROM cases").fetchone()[0],
        }


@app.get("/cases")
def list_cases(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    case_no: Optional[str] = Query(None, description="Exact case number, e.g. 425/2025"),
    court_level: Optional[str] = Query(None, description="MC, HC, or CA/SC"),
    institution: Optional[str] = Query(None, description="Exact institution — cases with a suspect there"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List hearings with full details, newest first. All filters optional."""
    where, params = [], []
    if date_from:
        where.append("hearing_date >= ?"); params.append(date_from)
    if date_to:
        where.append("hearing_date <= ?"); params.append(date_to)
    if case_no:
        where.append("case_no = ?"); params.append(case_no)
    if court_level:
        where.append("court_level = ?"); params.append(court_level)
    if institution:
        where.append("id IN (SELECT case_id FROM suspects WHERE institution = ?)")
        params.append(institution)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM cases {where_sql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT * FROM cases {where_sql}
                ORDER BY hearing_date DESC, case_no
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "cases": attach_children(conn, rows)}


@app.get("/suspects/search")
def search_suspects(
    q: str = Query(..., min_length=2, description="Name fragment, e.g. Rambukwella"),
    limit: int = Query(50, ge=1, le=200),
):
    """Search canonical names and aliases; return one result per person."""
    normalized_query = normalize_alias(q)
    with get_db() as conn:
        rows = conn.execute(
            """WITH matching_people AS (
                   SELECT DISTINCT p.id
                   FROM people p
                   JOIN person_aliases pa ON pa.person_id = p.id
                   WHERE LOWER(pa.alias) LIKE LOWER(?)
                      OR pa.normalized_alias LIKE ?
                   ORDER BY p.canonical_name
                   LIMIT ?
               )
               SELECT p.id AS person_id, p.canonical_name AS name,
                      s.name AS source_name, s.designation, s.institution,
                      c.hearing_date, c.case_no, c.court_level, c.source_pdf
               FROM matching_people mp
               JOIN people p ON p.id = mp.id
               JOIN suspects s ON s.person_id = p.id
               JOIN cases c ON s.case_id = c.id
               ORDER BY p.canonical_name, c.hearing_date, c.case_no""",
            (f"%{q}%", f"%{normalized_query}%", limit),
        ).fetchall()

        grouped: dict[int, dict] = {}
        for r in rows:
            entry = grouped.setdefault(
                r["person_id"],
                {
                    "person_id": r["person_id"],
                    "name": r["name"],
                    "aliases": set(),
                    "hearings": [],
                },
            )
            if r["source_name"] != r["name"]:
                entry["aliases"].add(r["source_name"])
            entry["hearings"].append(
                {
                    "date": r["hearing_date"],
                    "case_no": r["case_no"],
                    "court_level": r["court_level"],
                    "source_name": r["source_name"],
                    "designation": r["designation"],
                    "institution": r["institution"],
                    "source_pdf": r["source_pdf"],
                }
            )

        suspects = []
        for person in grouped.values():
            person["aliases"] = sorted(person["aliases"])
            suspects.append(person)
        return {"query": q, "matches": len(suspects), "suspects": suspects}


@app.get("/stats/institutions")
def institution_stats(limit: int = Query(20, ge=1, le=100)):
    """Institutions ranked by number of suspect records — dashboard bar chart."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT institution, COUNT(*) AS suspect_count,
                      COUNT(DISTINCT case_id) AS case_count
               FROM suspects WHERE institution IS NOT NULL
               GROUP BY institution ORDER BY suspect_count DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return {"institutions": [dict(r) for r in rows]}


@app.get("/stats/repeat-suspects")
def repeat_suspects(min_dates: int = Query(2, ge=2), limit: int = Query(20, ge=1, le=100)):
    """Suspects appearing on multiple hearing dates — 'most active cases' widget."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT s.person_id,
                      COALESCE(p.canonical_name, s.name) AS name,
                      COUNT(DISTINCT c.hearing_date) AS hearing_dates,
                      COUNT(DISTINCT c.case_no) AS case_numbers,
                      MIN(c.hearing_date) AS first_seen,
                      MAX(c.hearing_date) AS last_seen
               FROM suspects s
               LEFT JOIN people p ON p.id = s.person_id
               JOIN cases c ON s.case_id = c.id
               GROUP BY
                   CASE
                       WHEN s.person_id IS NOT NULL THEN 'person:' || s.person_id
                       ELSE 'name:' || LOWER(s.name)
                   END
               HAVING hearing_dates >= ?
               ORDER BY hearing_dates DESC, case_numbers DESC
               LIMIT ?""",
            (min_dates, limit),
        ).fetchall()
        return {"suspects": [dict(r) for r in rows]}


@app.get("/stats/hearings-per-date")
def hearings_per_date(
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None)
):
    """Hearings count per date — dashboard timeline chart."""
    where, params = [], []
    if date_from:
        where.append("hearing_date >= ?"); params.append(date_from)
    if date_to:
        where.append("hearing_date <= ?"); params.append(date_to)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT hearing_date, COUNT(*) AS hearings
                FROM cases {where_sql}
                GROUP BY hearing_date ORDER BY hearing_date""",
            params,
        ).fetchall()
        return {"timeline": [dict(r) for r in rows]}


@app.get("/stats/court-levels")
def court_levels():
    """Distribution of cases across court levels — dashboard pie chart."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT COALESCE(court_level, 'Unknown') AS court_level, COUNT(*) AS cases
               FROM cases GROUP BY court_level ORDER BY cases DESC"""
        ).fetchall()
        return {"court_levels": [dict(r) for r in rows]}


@app.get("/stats/court-trend")
def court_trend(
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None)
):
    """Hearings per date split by court level — stacked-area trend view.

    Pivoted server-side to one row per date with a column per court level,
    so Recharts can stack directly: [{hearing_date, HC, MC, "CA/SC", Unknown}].
    """
    where, params = [], []
    if date_from:
        where.append("hearing_date >= ?"); params.append(date_from)
    if date_to:
        where.append("hearing_date <= ?"); params.append(date_to)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT hearing_date,
                       COALESCE(court_level, 'Unknown') AS court_level,
                       COUNT(*) AS hearings
                FROM cases {where_sql}
                GROUP BY hearing_date, court_level
                ORDER BY hearing_date""",
            params,
        ).fetchall()

    levels: list[str] = []
    by_date: dict[str, dict] = {}
    for r in rows:
        lvl = r["court_level"]
        if lvl not in levels:
            levels.append(lvl)
        entry = by_date.setdefault(r["hearing_date"], {"hearing_date": r["hearing_date"]})
        entry[lvl] = r["hearings"]

    # backfill missing levels with 0 so stacks have no gaps
    timeline = []
    for d in sorted(by_date):
        row = by_date[d]
        for lvl in levels:
            row.setdefault(lvl, 0)
        timeline.append(row)

    return {"levels": levels, "timeline": timeline}

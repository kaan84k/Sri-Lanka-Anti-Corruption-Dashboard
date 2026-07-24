"""
CIABOC Anti-Corruption Dashboard - PDF Extraction Pipeline
===========================================================
PDF (court cause list) -> Gemini (structured JSON) -> Pydantic validation -> SQLite

Usage:
    export GEMINI_API_KEY="your-key-here"
    python pipeline/ciaboc_pipeline.py data/raw/20260112_-_20260116.pdf

Requirements:
    pip install google-genai pydantic
"""

import os
import re
import sys
import json
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from google import genai
from google.genai import types

# Paths resolve relative to the project root (parent of pipeline/), so the
# script works no matter which directory you run it from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_RAW = os.path.join(PROJECT_ROOT, "data", "raw")
DATA_PROCESSED = os.path.join(PROJECT_ROOT, "data", "processed")
REVIEW_DIR = os.path.join(DATA_PROCESSED, "review")
DB_PATH = os.path.join(DATA_PROCESSED, "ciaboc.db")

MODEL = "gemini-2.5-flash"  # cheap + good at document extraction; use gemini-2.5-pro if quality issues


# ---------------------------------------------------------------------------
# 1. Pydantic models — this schema is ALSO sent to Gemini as the output schema
# ---------------------------------------------------------------------------

class Suspect(BaseModel):
    name: str = Field(description="Full name of the suspect, cleaned up (fix merged words)")
    designation: Optional[str] = Field(default=None, description="Job title/position, e.g. 'Superintendent of Customs'")
    institution: Optional[str] = Field(default=None, description="Organization/workplace, e.g. 'Sri Lanka Customs'")


class Case(BaseModel):
    hearing_date: str = Field(description="Hearing date in YYYY-MM-DD format")
    file_nos: list[str] = Field(description="All file numbers, e.g. ['R/50/2011', 'BC/1104/2011']")
    case_no: str = Field(description="Case number, e.g. '425/2025'. Include bracketed old number if present.")
    court_level: Optional[str] = Field(
        default=None,
        description="Which court column has the asterisk: 'MC', 'HC', or 'CA/SC'. Null if unclear."
    )
    suspects: list[Suspect]

    # ---- validation rules ----
    @field_validator("hearing_date")
    @classmethod
    def valid_date(cls, v: str) -> str:
        datetime.strptime(v, "%Y-%m-%d")  # raises ValueError if wrong
        return v

    @field_validator("case_no")
    @classmethod
    def valid_case_no(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("case_no is empty")
        return v

    @field_validator("file_nos")
    @classmethod
    def clean_file_nos(cls, v: list[str]) -> list[str]:
        cleaned = [f.strip() for f in v if f and f.strip()]
        if not cleaned:
            raise ValueError("no file numbers found")
        return cleaned

    @field_validator("suspects")
    @classmethod
    def at_least_one_suspect(cls, v: list[Suspect]) -> list[Suspect]:
        if not v:
            raise ValueError("case has no suspects")
        return v


class ExtractionResult(BaseModel):
    cases: list[Case]


# ---------------------------------------------------------------------------
# 2. Gemini extraction
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are extracting data from a Sri Lankan CIABOC (Commission to
Investigate Allegations of Bribery or Corruption) court cause list PDF.

The PDF is a table with columns: DATE | FILE NO. | CASE NO. | MC | HC | CA/SC | SUSPECT/S
The asterisk (*) marks which court column applies (MC, HC, or CA/SC).

Extract EVERY case row in the document. Rules:
1. Dates appear as DD/MM/YYYY in the PDF — convert to YYYY-MM-DD.
2. A case may have multiple file numbers stacked in one cell — capture all of them.
3. A case may have multiple numbered suspects — capture each as a separate suspect
   with name, designation, and institution split into separate fields.
4. The PDF has broken text where words merge together (e.g. "B.S.PriyadarshanaExcise Officer"
   means name "B.S. Priyadarshana", designation "Excise Officer"). Fix these intelligently.
5. Fix obvious typos in institution names (e.g. "Prisident College" -> "President College",
   "Parliment" -> "Parliament") but NEVER change personal names or case/file numbers.
6. Some dates have no cases (e.g. a public holiday like "Tamil Thaipongal Day") — skip those.
7. Do not invent data. If a field is genuinely missing, use null.

Return every case. Do not skip any rows."""


def extract_with_gemini(pdf_path: str, api_key: str) -> ExtractionResult:
    """Send the PDF to Gemini and get back schema-enforced JSON."""
    client = genai.Client(api_key=api_key)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractionResult,   # Gemini enforces this schema
            temperature=0.0,                    # deterministic: we want facts, not creativity
        ),
    )

    # response.parsed gives us a ready Pydantic object; fall back to manual parse
    if response.parsed is not None:
        return response.parsed
    return ExtractionResult.model_validate_json(response.text)


# ---------------------------------------------------------------------------
# 3. Post-extraction validation (things Pydantic alone can't check)
# ---------------------------------------------------------------------------

FILE_NO_PATTERN = re.compile(r"^(R|BC|AC)\s*/?\s*\d+", re.IGNORECASE)

def validate_cases(result: ExtractionResult, pdf_name: str) -> tuple[list[Case], list[dict]]:
    """Separate good cases from rejected ones. Never silently drop data —
    rejected rows go to a review file so a human can fix them."""
    good, rejected = [], []
    seen = set()

    for case in result.cases:
        problems = []

        # duplicate check (same case can legitimately appear on different dates)
        key = (case.case_no, case.hearing_date)
        if key in seen:
            problems.append("duplicate case_no + date in same PDF")
        seen.add(key)

        # sanity: hearing date should be within a plausible range
        year = int(case.hearing_date[:4])
        if not (2000 <= year <= 2035):
            problems.append(f"implausible hearing year {year}")

        # sanity: at least one file number should look like a real CIABOC file no.
        if not any(FILE_NO_PATTERN.match(f) for f in case.file_nos):
            problems.append(f"no recognizable file number in {case.file_nos}")

        # sanity: suspect names shouldn't be suspiciously short
        for s in case.suspects:
            if len(s.name.strip()) < 3:
                problems.append(f"suspect name too short: '{s.name}'")

        if problems:
            rejected.append({"case": case.model_dump(), "problems": problems, "source_pdf": pdf_name})
        else:
            good.append(case)

    return good, rejected


# ---------------------------------------------------------------------------
# 4. SQLite storage
# ---------------------------------------------------------------------------

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    case_no      TEXT NOT NULL,
    hearing_date TEXT NOT NULL,          -- ISO YYYY-MM-DD, sortable as text
    court_level  TEXT,
    source_pdf   TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    UNIQUE (case_no, hearing_date)       -- same case, same date = same hearing
);

CREATE TABLE IF NOT EXISTS file_numbers (
    case_id  INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    file_no  TEXT NOT NULL,
    UNIQUE (case_id, file_no)
);

CREATE TABLE IF NOT EXISTS suspects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    designation TEXT,
    institution TEXT
);

CREATE INDEX IF NOT EXISTS idx_cases_date     ON cases(hearing_date);
CREATE INDEX IF NOT EXISTS idx_suspects_name  ON suspects(name);
CREATE INDEX IF NOT EXISTS idx_suspects_inst  ON suspects(institution);
"""


def save_to_sqlite(cases: list[Case], pdf_name: str, db_path: str = DB_PATH) -> tuple[int, int]:
    """Insert cases. Re-running on the same PDF won't create duplicates."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    inserted = skipped = 0
    now = datetime.now().isoformat(timespec="seconds")

    try:
        for case in cases:
            cur = conn.execute(
                """INSERT OR IGNORE INTO cases (case_no, hearing_date, court_level, source_pdf, extracted_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (case.case_no, case.hearing_date, case.court_level, pdf_name, now),
            )
            if cur.rowcount == 0:          # already existed -> skip children too
                skipped += 1
                continue
            inserted += 1
            case_id = cur.lastrowid

            conn.executemany(
                "INSERT OR IGNORE INTO file_numbers (case_id, file_no) VALUES (?, ?)",
                [(case_id, f) for f in case.file_nos],
            )
            conn.executemany(
                "INSERT INTO suspects (case_id, name, designation, institution) VALUES (?, ?, ?, ?)",
                [(case_id, s.name, s.designation, s.institution) for s in case.suspects],
            )
        conn.commit()
    finally:
        conn.close()
    return inserted, skipped


# ---------------------------------------------------------------------------
# 5. Main pipeline
# ---------------------------------------------------------------------------

def run(pdf_path: str):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERROR: set GEMINI_API_KEY environment variable first.")
    if not os.path.exists(pdf_path):
        sys.exit(f"ERROR: file not found: {pdf_path}")

    # ensure data/processed/ and data/processed/review/ exist
    os.makedirs(REVIEW_DIR, exist_ok=True)

    pdf_name = os.path.basename(pdf_path)
    print(f"[1/4] Sending {pdf_name} to Gemini ({MODEL}) ...")
    result = extract_with_gemini(pdf_path, api_key)
    print(f"      Gemini returned {len(result.cases)} cases")

    print("[2/4] Validating ...")
    good, rejected = validate_cases(result, pdf_name)
    print(f"      {len(good)} passed, {len(rejected)} rejected")

    if rejected:
        review_file = os.path.join(
            REVIEW_DIR, f"review_{hashlib.md5(pdf_name.encode()).hexdigest()[:8]}.json"
        )
        with open(review_file, "w", encoding="utf-8") as f:
            json.dump(rejected, f, indent=2, ensure_ascii=False)
        print(f"      Rejected rows written to {review_file} — check them manually")

    print(f"[3/4] Saving to {DB_PATH} ...")
    inserted, skipped = save_to_sqlite(good, pdf_name)
    print(f"      {inserted} inserted, {skipped} already existed (skipped)")

    print("[4/4] Done. Quick stats:")
    conn = sqlite3.connect(DB_PATH)
    total_cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    total_suspects = conn.execute("SELECT COUNT(*) FROM suspects").fetchone()[0]
    conn.close()
    print(f"      Database now holds {total_cases} hearings / {total_suspects} suspect records")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python ciaboc_pipeline.py <path-to-pdf>")
    run(sys.argv[1])

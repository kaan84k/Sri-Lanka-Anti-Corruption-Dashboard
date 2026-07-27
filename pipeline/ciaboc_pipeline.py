"""
CIABOC Anti-Corruption Dashboard - PDF Extraction Pipeline
===========================================================
PDF (court cause list) -> Gemini (structured JSON) -> Pydantic validation -> SQLite

Usage:
    export GEMINI_API_KEY="your-key-here"
    python ciaboc_pipeline.py path/to/20260112_-_20260116.pdf

Requirements:
    pip install google-genai pydantic
"""

import os
import re
import sys
import json
import time
import sqlite3
import hashlib
from datetime import date, datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # court-level resolution degrades gracefully if missing

try:
    from .identity_resolution import initialize_identity_schema, resolve_person_id
except ImportError:
    from identity_resolution import initialize_identity_schema, resolve_person_id

# Paths resolve relative to the project root (parent of pipeline/), so the
# script works no matter which directory you run it from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_RAW = os.path.join(PROJECT_ROOT, "data", "raw")
DATA_PROCESSED = os.path.join(PROJECT_ROOT, "data", "processed")
REVIEW_DIR = os.path.join(DATA_PROCESSED, "review")
DB_PATH = os.path.join(DATA_PROCESSED, "ciaboc.db")

FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",  # optimized for high-volume document extraction
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]
MODEL = FALLBACK_MODELS[0]
MAX_RETRIES_PER_MODEL = 4   # with exponential backoff: waits 5s, 10s, 20s, 40s


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


class ExtractedSuspect(BaseModel):
    """Permissive Gemini output; strict validation happens after extraction."""

    name: Optional[str]
    designation: Optional[str]
    institution: Optional[str]


class ExtractedCase(BaseModel):
    """Raw case shape that preserves incomplete rows for manual review."""

    hearing_date: Optional[str]
    file_nos: Optional[list[str]]
    case_no: Optional[str]
    court_level: Optional[str]
    suspects: Optional[list[ExtractedSuspect]]


class ExtractionResult(BaseModel):
    cases: list[ExtractedCase]


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
    """Send the PDF to Gemini and get back schema-enforced JSON.

    Handles temporary server overload (503) and rate limits (429):
    retries each model with exponential backoff, then falls back to
    the next model in FALLBACK_MODELS.
    """
    client = genai.Client(api_key=api_key)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    contents = [
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        EXTRACTION_PROMPT,
    ]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ExtractionResult,   # Gemini enforces this schema
    )

    last_error = None
    for model in FALLBACK_MODELS:
        for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
            try:
                response = client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                if model != FALLBACK_MODELS[0]:
                    print(f"      (note: used fallback model {model})")
                if response.parsed is not None:
                    return response.parsed
                return ExtractionResult.model_validate_json(response.text)

            except genai_errors.APIError as e:
                last_error = e
                # A retired/unavailable model should immediately fall through
                # to the next model instead of aborting the whole pipeline.
                if e.code == 404:
                    print(f"      {model} unavailable (404), trying next model ...")
                    break

                # 503 = overloaded, 429 = rate limited -> both are temporary
                if e.code in (503, 429):
                    if attempt < MAX_RETRIES_PER_MODEL:
                        wait = 5 * (2 ** (attempt - 1))     # 5, 10, 20, 40 seconds
                        print(f"      {model} busy ({e.code}), retry {attempt}/{MAX_RETRIES_PER_MODEL - 1} in {wait}s ...")
                        time.sleep(wait)
                    else:
                        print(f"      {model} still busy after {MAX_RETRIES_PER_MODEL} tries, trying next model ...")
                else:
                    raise  # real errors (bad API key, invalid request) should fail loudly

    sys.exit(f"ERROR: all models busy after retries. Try again in a few minutes.\nLast error: {last_error}")


# ---------------------------------------------------------------------------
# 2b. Court-level resolution from PDF geometry (ground truth the LLM can't see)
# ---------------------------------------------------------------------------
# The cause-list table marks the applicable court with a single "*" in one of
# three adjacent columns (MC | HC | C.A/S.C). When the PDF text is flattened for
# the LLM, the column the asterisk sits in is lost, so the model guesses — and
# tends to default everything to MC. We instead read the asterisk's X coordinate
# and map it to the nearest court-column header, which is deterministic.

_COURT_HEADERS = {"MC": "MC", "HC": "HC", "C.A": "CA/SC"}
_COURT_NA = "N/A"          # row present in the PDF but its court column is blank
_CASE_COL_X = (150, 235)   # x-range of the CASE NO. column
_ROW_TOL = 8               # vertical px tolerance pairing an asterisk with a case row
_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _norm_case_no(case_no: Optional[str]) -> str:
    """Match key for a case number: primary number, no bracketed alias, no spaces."""
    if not case_no:
        return ""
    return re.split(r"\s*\(", case_no.strip())[0].replace(" ", "").upper()


def resolve_court_levels(pdf_path: str) -> dict[str, str]:
    """Map {normalized_case_no: court_level} by asterisk column position.

    Returns {} if pdfplumber is unavailable so the caller can fall back cleanly.
    """
    if pdfplumber is None:
        print("      (pdfplumber not installed — skipping court-level correction)")
        return {}

    out: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            cols = {
                w["text"]: (w["x0"] + w["x1"]) / 2
                for w in words
                if w["text"] in _COURT_HEADERS and w["top"] < 120
            }
            if not cols:
                continue
            # Case numbers can be split across several tokens on the same line
            # (e.g. "441/2025" -> "4" + "41/2025"). Group case-column tokens by
            # their vertical position and concatenate them left-to-right so the
            # whole number reassembles before matching.
            grouped: dict[int, list] = {}
            for w in words:
                if (
                    _CASE_COL_X[0] < w["x0"] < _CASE_COL_X[1]
                    and re.search(r"\d", w["text"])
                    and not _DATE_RE.match(w["text"])
                ):
                    grouped.setdefault(round(w["top"]), []).append((w["x0"], w["text"]))
            rows = [
                ("".join(t for _, t in sorted(frags)), top)
                for top, frags in grouped.items()
            ]
            starred = set()
            for w in words:
                if w["text"] != "*":
                    continue
                cx = (w["x0"] + w["x1"]) / 2
                court = _COURT_HEADERS[min(cols, key=lambda k: abs(cols[k] - cx))]
                near = min(rows, key=lambda r: abs(r[1] - w["top"]), default=None)
                if near and abs(near[1] - w["top"]) <= _ROW_TOL:
                    key = _norm_case_no(near[0])
                    out[key] = court
                    starred.add(round(near[1]))
            # Rows we located but that carry no asterisk have a blank court
            # column in the source document -> record as 'N/A' (marked-absent),
            # kept distinct from cases we couldn't locate at all (left unset).
            for text, top in rows:
                key = _norm_case_no(text)
                if key and round(top) not in starred and key not in out:
                    out[key] = _COURT_NA
    return out


def apply_court_levels(result: "ExtractionResult", pdf_path: str) -> int:
    """Overwrite each case's court_level with the geometry-derived value.

    Coordinates are authoritative: where an asterisk column is found we use it;
    where none is found we set None (Unknown) rather than trust the LLM's guess.
    Returns the number of cases whose court_level changed.
    """
    court_by_case = resolve_court_levels(pdf_path)
    if not court_by_case:
        return 0
    changed = 0
    for case in result.cases:
        resolved = court_by_case.get(_norm_case_no(case.case_no))
        if resolved != case.court_level:
            case.court_level = resolved
            changed += 1
    return changed


# ---------------------------------------------------------------------------
# 2c. Hearing-date repair against the week the PDF covers
# ---------------------------------------------------------------------------
# Cause-list filenames encode the week: 20260126_-_20260130.pdf = 26-30 Jan 2026.
# Gemini sometimes drifts the year along with the day when reading a column of
# dates (26/01/2026, 27/01/2026 ... came back as 2026-01-26, 2027-01-27,
# 2028-01-28 ...). The filename window is ground truth, so a date whose day and
# month land inside the window but whose year does not is corrected to the
# window's year; anything else is left alone for validation to reject.

_PDF_WEEK_RE = re.compile(r"(\d{8})\D+(\d{8})")


def pdf_date_window(pdf_name: str) -> Optional[tuple[date, date]]:
    """First and last hearing date the PDF covers, taken from its filename."""
    m = _PDF_WEEK_RE.search(pdf_name)
    if not m:
        return None
    try:
        start = datetime.strptime(m.group(1), "%Y%m%d").date()
        end = datetime.strptime(m.group(2), "%Y%m%d").date()
    except ValueError:
        return None
    if end < start or (end - start).days > 31:
        return None
    return start, end


def _window_days(window: tuple[date, date]) -> list[date]:
    start, end = window
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def repair_hearing_dates(result: ExtractionResult, pdf_name: str) -> int:
    """Fix wrong-year hearing dates using the PDF filename's week. Returns count fixed."""
    window = pdf_date_window(pdf_name)
    if window is None:
        return 0
    by_day_month = {(d.month, d.day): d for d in _window_days(window)}
    fixed = 0
    for case in result.cases:
        if not case.hearing_date:
            continue
        try:
            parsed = datetime.strptime(case.hearing_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if window[0] <= parsed <= window[1]:
            continue
        corrected = by_day_month.get((parsed.month, parsed.day))
        if corrected is not None:
            case.hearing_date = corrected.isoformat()
            fixed += 1
    return fixed


# ---------------------------------------------------------------------------
# 3. Post-extraction validation (things Pydantic alone can't check)
# ---------------------------------------------------------------------------

FILE_NO_PATTERN = re.compile(r"^(R|BC|AC)\s*/?\s*\d+", re.IGNORECASE)

def validate_cases(result: ExtractionResult, pdf_name: str) -> tuple[list[Case], list[dict]]:
    """Separate good cases from rejected ones. Never silently drop data —
    rejected rows go to a review file so a human can fix them."""
    good, rejected = [], []
    seen = set()
    window = pdf_date_window(pdf_name)

    for extracted_case in result.cases:
        raw_case = extracted_case.model_dump()
        try:
            case = Case.model_validate(raw_case)
        except ValidationError as exc:
            problems = [
                f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
                for error in exc.errors()
            ]
            rejected.append({
                "case": raw_case,
                "problems": problems,
                "source_pdf": pdf_name,
            })
            continue

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

        # sanity: the date must fall inside the week the PDF covers. Catches
        # model drift (e.g. 27/01/2026 read back as 2027-01-27) that the plain
        # year range above is far too loose to notice.
        if window is not None:
            hearing = datetime.strptime(case.hearing_date, "%Y-%m-%d").date()
            if not (window[0] <= hearing <= window[1]):
                problems.append(
                    f"hearing date {case.hearing_date} outside PDF week "
                    f"{window[0].isoformat()}..{window[1].isoformat()}"
                )

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
    initialize_identity_schema(conn)
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
            suspect_rows = [
                (
                    case_id,
                    s.name,
                    s.designation,
                    s.institution,
                    resolve_person_id(conn, s.name),
                )
                for s in case.suspects
            ]
            conn.executemany(
                """INSERT INTO suspects
                       (case_id, name, designation, institution, person_id)
                   VALUES (?, ?, ?, ?, ?)""",
                suspect_rows,
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

    print("[1b] Resolving court levels from PDF geometry ...")
    changed = apply_court_levels(result, pdf_path)
    print(f"      Corrected court_level on {changed} case(s) via asterisk position")

    print("[1c] Checking hearing dates against the PDF's week ...")
    fixed = repair_hearing_dates(result, pdf_name)
    print(f"      Corrected wrong-year hearing date on {fixed} case(s)")

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

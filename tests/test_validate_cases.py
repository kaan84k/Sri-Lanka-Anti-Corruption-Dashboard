"""Tests for validate_cases() — the good/rejected split.

Every rejection asserted here corresponds to a real row in
docs/rejected-rows-report.md. The point is that rejected rows stay rejected for
the stated reason, and that the four rows recovered in section A stay accepted.
"""

import pytest

from pipeline.ciaboc_pipeline import ExtractedCase, ExtractionResult, validate_cases

PDF = "20260216_-_20260220.pdf"


def make_case(**overrides):
    fields = {
        "hearing_date": "2026-02-17",
        "file_nos": ["BC/C/1133/2016"],
        "case_no": "450/2025",
        "court_level": "HC",
        "suspects": [
            {
                "name": "Chamara Sampath Dasanayake",
                "designation": "Former Chief Minister",
                "institution": "Uva Province",
            }
        ],
    }
    fields.update(overrides)
    return ExtractedCase.model_validate(fields)


def run(*cases, pdf_name=PDF):
    return validate_cases(ExtractionResult(cases=list(cases)), pdf_name)


def problems_of(rejected):
    return " | ".join(rejected["problems"])


def test_sub_coded_file_number_is_accepted():
    """The 2026-02-17 Uva Province row, lost for five weeks to the regex bug."""
    good, rejected = run(make_case())
    assert rejected == []
    assert len(good) == 1
    assert good[0].file_nos == ["BC/C/1133/2016"]
    assert good[0].suspects[0].name == "Chamara Sampath Dasanayake"


def test_rejected_rows_carry_the_source_pdf():
    _, rejected = run(make_case(file_nos=None))
    assert rejected[0]["source_pdf"] == PDF
    assert rejected[0]["case"]["case_no"] == "450/2025"


# --- appellate / writ shapes (report section B) ------------------------------

def test_null_file_nos_is_rejected():
    good, rejected = run(make_case(file_nos=None, suspects=[]))
    assert good == []
    assert "file_nos: Input should be a valid list" in problems_of(rejected[0])


def test_empty_file_nos_is_rejected():
    good, rejected = run(make_case(file_nos=[], suspects=[]))
    assert good == []
    assert "no file numbers found" in problems_of(rejected[0])


def test_null_case_no_is_rejected():
    good, rejected = run(
        make_case(case_no=None, file_nos=["CA/HCC 177/2025"], suspects=[])
    )
    assert good == []
    assert "case_no: Input should be a valid string" in problems_of(rejected[0])


def test_case_with_no_suspects_is_rejected():
    good, rejected = run(make_case(suspects=[]))
    assert good == []
    assert "case has no suspects" in problems_of(rejected[0])


def test_appellate_identifier_in_file_nos_is_not_a_file_number():
    """Passes Pydantic (non-empty list, named suspect) but fails the shape check."""
    good, rejected = run(make_case(file_nos=["SC/SPL/LA 182/2025"]))
    assert good == []
    assert "no recognizable file number" in problems_of(rejected[0])


# --- other validators --------------------------------------------------------

def test_hearing_date_outside_the_pdf_week_is_rejected():
    good, rejected = run(make_case(hearing_date="2027-02-17"))
    assert good == []
    assert "outside PDF week 2026-02-16..2026-02-20" in problems_of(rejected[0])


def test_same_case_on_different_days_is_kept():
    """CA/CPA/02/2026 ran three consecutive days — not a duplicate extraction."""
    good, rejected = run(
        make_case(hearing_date="2026-02-17"),
        make_case(hearing_date="2026-02-18"),
    )
    assert rejected == []
    assert len(good) == 2


def test_same_case_on_the_same_day_is_a_duplicate():
    good, rejected = run(make_case(), make_case())
    assert len(good) == 1
    assert "duplicate case_no + date in same PDF" in problems_of(rejected[0])


def test_short_suspect_name_is_rejected():
    good, rejected = run(
        make_case(suspects=[{"name": "AB", "designation": None, "institution": None}])
    )
    assert good == []
    assert "suspect name too short" in problems_of(rejected[0])


@pytest.mark.parametrize("bad_date", ["17-02-2026", "2026-13-01", "not a date"])
def test_malformed_hearing_date_is_rejected(bad_date):
    good, rejected = run(make_case(hearing_date=bad_date))
    assert good == []
    assert "hearing_date" in problems_of(rejected[0])

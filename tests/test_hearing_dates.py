"""Regression tests for the PDF-week date repair (pipeline step 1c).

Gemini drifted the year along with the day when reading a column of dates
(26/01, 27/01, 28/01 came back as 2026, 2027, 2028). The filename window is
ground truth; a date whose day and month land inside the window but whose year
does not is corrected. Anything else is left alone for validate_cases to reject.
"""

from datetime import date

import pytest

from pipeline.ciaboc_pipeline import (
    ExtractedCase,
    ExtractionResult,
    pdf_date_window,
    repair_hearing_dates,
)


def make_case(hearing_date):
    return ExtractedCase(
        hearing_date=hearing_date,
        file_nos=["BC/1104/2011"],
        case_no="425/2025",
        court_level="HC",
        suspects=[],
    )


# --- pdf_date_window ---------------------------------------------------------

def test_window_from_filename():
    assert pdf_date_window("20260126_-_20260130.pdf") == (
        date(2026, 1, 26),
        date(2026, 1, 30),
    )


@pytest.mark.parametrize(
    "pdf_name",
    [
        "cause_list.pdf",            # no dates at all
        "20260130_-_20260126.pdf",   # end before start
        "20260101_-_20260401.pdf",   # span longer than a month
        "20261301_-_20261305.pdf",   # month 13
    ],
)
def test_unusable_filenames_yield_no_window(pdf_name):
    assert pdf_date_window(pdf_name) is None


# --- repair_hearing_dates ----------------------------------------------------

def test_drifted_year_is_corrected_to_the_pdf_week():
    result = ExtractionResult(cases=[make_case("2027-01-27"), make_case("2028-01-28")])
    assert repair_hearing_dates(result, "20260126_-_20260130.pdf") == 2
    assert [c.hearing_date for c in result.cases] == ["2026-01-27", "2026-01-28"]


def test_dates_already_inside_the_window_are_untouched():
    result = ExtractionResult(cases=[make_case("2026-01-26")])
    assert repair_hearing_dates(result, "20260126_-_20260130.pdf") == 0
    assert result.cases[0].hearing_date == "2026-01-26"


def test_day_month_outside_the_window_is_left_for_validation():
    """Only the year is ever rewritten — a 15 March date is a real extraction
    error, not year drift, and must survive to be rejected."""
    result = ExtractionResult(cases=[make_case("2026-03-15")])
    assert repair_hearing_dates(result, "20260126_-_20260130.pdf") == 0
    assert result.cases[0].hearing_date == "2026-03-15"


def test_no_window_means_no_repair():
    result = ExtractionResult(cases=[make_case("2027-01-27")])
    assert repair_hearing_dates(result, "cause_list.pdf") == 0
    assert result.cases[0].hearing_date == "2027-01-27"

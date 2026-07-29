"""Regression tests for FILE_NO_PATTERN.

Background: the original pattern required a digit immediately after the prefix,
so CIABOC file numbers carrying a one-letter sub-code (BC/C/1133/2016,
BC/O/1203/2016) were rejected as "no recognizable file number" and the rows were
dropped. See docs/rejected-rows-report.md section A.

The pattern must keep rejecting appellate/writ identifiers (SC/..., CA/...,
LTA/..., HC/TAB/...), which are a genuinely different record type — the review
file is the only signal that those rows exist at all.
"""

import pytest

from pipeline.ciaboc_pipeline import FILE_NO_PATTERN

# Sub-coded file numbers — the four rows lost to the regex bug.
SUB_CODED = [
    "BC/C/1087/2016",
    "BC/C/2331/2016",
    "BC/C/1133/2016",
    "BC/O/1203/2016",
]

# Plain forms that were always accepted; guard against over-tightening.
PLAIN = [
    "R/50/2011",
    "BC/1104/2011",
    "AC/12/2019",
    "R50/2011",
    "BC 1104/2011",
    "bc/c/1133/2016",
]

# Appellate / writ identifiers — must stay rejected.
APPELLATE = [
    "SC/SPL/LA 182/2025",
    "SC/SPL/LA 304/2025",
    "SCFR 22/2023",
    "SC FR 203/2024",
    "SC/FR/146/2024",
    "SC/FR 171/25",
    "CA/HCC/103/2024",
    "CA/HCC 177/2025",
    "CA/Writ/589/2025",
    "CA Writ 762/2025",
    "CA/CPA/02/2026",
    "CA/LTA 17/2024",
    "LTA/17/2026",
    "HC/TAB/02/2025",
]


@pytest.mark.parametrize("file_no", SUB_CODED)
def test_lettered_sub_codes_match(file_no):
    assert FILE_NO_PATTERN.match(file_no)


@pytest.mark.parametrize("file_no", PLAIN)
def test_plain_file_numbers_match(file_no):
    assert FILE_NO_PATTERN.match(file_no)


@pytest.mark.parametrize("identifier", APPELLATE)
def test_appellate_identifiers_do_not_match(identifier):
    assert not FILE_NO_PATTERN.match(identifier)


def test_sub_code_is_a_single_letter_only():
    """Two-letter sub-codes are not a known CIABOC form; keep them out so the
    pattern does not start swallowing appellate prefixes."""
    assert not FILE_NO_PATTERN.match("BC/CO/1133/2016")

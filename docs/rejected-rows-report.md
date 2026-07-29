# Rejected Rows Report

Audit of every file in `data/processed/review/` as of 2026-07-28.
Source: `validate_cases()` in `pipeline/ciaboc_pipeline.py:374`.
Follow-up actions closed out 2026-07-29 — see [Recommended order](#recommended-order).

**28 rejected rows across 5 weekly PDFs.** Two distinct root causes:

| Root cause | Rows | Verdict |
|---|---|---|
| A. `FILE_NO_PATTERN` regex rejects lettered sub-codes (`BC/C/`, `BC/O/`) | 4 | **Bug — false rejects, real data lost.** Fixed and recovered 2026-07-28 |
| B. Appellate / writ calendar entries carry no CIABOC file number and no named suspect | 24 | Correct reject, but schema mismatch — these rows are unrepresentable. Deferred 2026-07-29, no owner |

The `.bak` files (`review_c67af4c7.json.bak`, `review_f8b6b836.json.bak`) are byte-identical copies of their siblings and are excluded from the counts.

---

## A. False rejects — regex bug (4 rows, HIGH priority)

The pattern as it stood (now at `pipeline/ciaboc_pipeline.py:372`):

```python
FILE_NO_PATTERN = re.compile(r"^(R|BC|AC)\s*/?\s*\d+", re.IGNORECASE)
```

The pattern demands a digit immediately after the prefix. CIABOC file numbers with a one-letter sub-code (`BC/C/1133/2016`, `BC/O/1203/2016`) never match, so `validate_cases` appends `no recognizable file number` and the row is dropped.

Confirmed by DB inspection: `SELECT file_no FROM file_numbers WHERE file_no LIKE '%/C/%' OR file_no LIKE '%/O/%'` returns **zero rows**. Every lettered-sub-code case that has ever been extracted has been rejected. Prefix distribution currently in the DB is `BC/` 326, `R/` 179, `AC/` 22 — all digit-after-prefix forms only.

These four rows have complete, valid suspect data. They are pure data loss.

| Source PDF | Hearing | File no | Case no | Court | Suspects |
|---|---|---|---|---|---|
| `20260126_-_20260130.pdf` | 2026-01-27 | `BC/C/1087/2016` | 364/2025 | HC | Helamba Arachchilage Don Anjana Srinath — Local Council Member, Gampaha Pradeshiya Sabhawa |
| `20260216_-_20260220.pdf` | 2026-02-16 | `BC/C/2331/2016` | 212/2023 | HC | S.K.R. Asela Kumara |
| `20260216_-_20260220.pdf` | 2026-02-17 | `BC/C/1133/2016` | 450/2025 | HC | **Chamara Sampath Dasanayake — Former Chief Minister, Uva Province**; A.B.M.W. Jayalath — Former Private Secretary to the Chief Minister, Uva Province |
| `20260216_-_20260220.pdf` | 2026-02-19 | `BC/O/1203/2016` | 304/2024 | HC | Y.M.K. Manjula — Land Officer, Mahaweli Authority H Region; J. Hettiarachchi — Unit Manager, Thalawa |

The 2026-02-17 row is a high-profile prosecution of a former provincial Chief Minister. It is missing from the dashboard entirely.

### Fix

Allow an optional single-letter sub-code between the prefix and the number:

```python
FILE_NO_PATTERN = re.compile(r"^(R|BC|AC)\s*/?\s*(?:[A-Z]\s*/?\s*)?\d+", re.IGNORECASE)
```

Observed sub-codes so far are `C` and `O`.

### Status: fixed 2026-07-28

Patch applied at `pipeline/ciaboc_pipeline.py:372`. Checked against 9 valid file
numbers (now all match) and 8 appellate identifiers from section B (still all
rejected) — no regression in either direction.

The four rows were recovered by replaying them from the review JSON rather than
re-running Gemini. The review file stores the post-`Case` dict, so the court-level
resolution (step 1b) and hearing-date repair (step 1c) were already baked in;
re-validation is faithful and deterministic. All four passed and inserted cleanly:

```
cases        323 -> 327
suspects     474 -> 480
suspects with unresolved person_id: 0
```

Verified in the DB — all six suspects present with designation, institution, and a
populated `person_id`, including both Uva Province defendants on case 450/2025.

Not done: a full Gemini re-run of the two PDFs. `GEMINI_API_KEY` is not set in the
process, user, or machine environment, so the pipeline cannot be invoked
non-interactively. A full re-run would additionally catch any *other* row those PDFs
lost for reasons not visible in the review JSON, but no such rows are known.

### Locked in by tests 2026-07-29

`tests/test_file_no_pattern.py` pins the pattern from both sides: the four
sub-coded numbers and six plain forms must match, fourteen appellate/writ
identifiers must not, and a two-letter sub-code (`BC/CO/…`) must not — that last
one is the guard against a future "just make it more permissive" edit sliding the
section B rows into section A's shape.

---

## B. Appellate / writ entries with no suspects (24 rows, MEDIUM priority)

These are Supreme Court, Court of Appeal, writ, and tribunal matters listed on the CIABOC calendar. In the source PDF they occupy a row with a case number but no CIABOC investigation file number and no accused-party column — the Commission is typically the respondent, not the prosecutor. The extraction is faithful; the `Case` model simply cannot represent them.

Three validators fire, all on the same underlying shape:

- `file_nos: Value error, no file numbers found` — Gemini returned `[]` (13 rows)
- `file_nos: Input should be a valid list` — Gemini returned `null` (6 rows)
- `case_no: Input should be a valid string` — Gemini returned `null`, putting the identifier in `file_nos` instead (5 rows)

All 24 also trip `suspects: Value error, case has no suspects`.

### Breakdown by PDF

**`20260119_-_20260123.pdf`** (`review_f8b6b836.json`) — 2 rows

| Hearing | Identifier | Court | Failure |
|---|---|---|---|
| 2026-01-19 | CA/HCC/103/2024 | CA/SC | empty `file_nos`, no suspects |
| 2026-01-20 | HC/TAB/02/2025, HC/TAB/03/2025 | null | null `case_no`, no suspects |

**`20260126_-_20260130.pdf`** (`review_c67af4c7.json`) — 6 rows (7th is the regex bug above)

| Hearing | Identifier | Court | Failure |
|---|---|---|---|
| 2026-01-26 | CA/Writ/589/2025 | CA/SC | null `file_nos`, no suspects |
| 2026-01-26 | SCFR 22/2023 | null | null `file_nos`, no suspects |
| 2026-01-26 | SC/SPL/LA 304/2025 | null | null `file_nos`, no suspects |
| 2026-01-29 | CA/Writ/748/2025 | null | null `file_nos`, no suspects |
| 2026-01-30 | CA Writ 762/2025 | null | null `file_nos`, no suspects |
| 2026-01-30 | SC/FR/146/2024 | CA/SC | null `file_nos`, no suspects |

**`20260202_-_20260206.pdf`** (`review_4a583882.json`) — 1 row

| Hearing | Identifier | Court | Failure |
|---|---|---|---|
| 2026-02-02 | SC/SPL/LA 182/2025 | null | empty `file_nos`, no suspects |

**`20260209_-_20260213.pdf`** (`review_2884cffb.json`) — 11 rows

| Hearing | Identifier | Court | Failure |
|---|---|---|---|
| 2026-02-09 | SC FR 203/2024 | null | empty `file_nos`, no suspects |
| 2026-02-09 | SC FR 204/2024 | null | empty `file_nos`, no suspects |
| 2026-02-09 | SC FR 205/2024 | null | empty `file_nos`, no suspects |
| 2026-02-09 | SC FR 218/2024 | null | empty `file_nos`, no suspects |
| 2026-02-09 | SC FR 219/2024 | null | empty `file_nos`, no suspects |
| 2026-02-09 | CA/CPA/02/2026 | CA/SC | empty `file_nos`, no suspects |
| 2026-02-09 | CA/CPA/03/2026 | CA/SC | empty `file_nos`, no suspects |
| 2026-02-10 | CA/CPA/02/2026 | CA/SC | empty `file_nos`, no suspects |
| 2026-02-10 | CA/CPA/03/2026 | CA/SC | empty `file_nos`, no suspects |
| 2026-02-11 | CA/CPA/02/2026 | CA/SC | empty `file_nos`, no suspects |
| 2026-02-11 | CA/CPA/03/2026 | CA/SC | empty `file_nos`, no suspects |

`CA/CPA/02/2026` and `CA/CPA/03/2026` each appear on three consecutive days — a
continuous hearing, not a duplicate extraction. Any future ingestion of these rows
must keep all three dates.

**`20260216_-_20260220.pdf`** (`review_b6e3ba31.json`) — 4 rows (other 3 are the regex bug above)

| Hearing | Identifier | Court | Failure |
|---|---|---|---|
| 2026-02-19 | CA/CPA 03/2026 | null | null `case_no`, no suspects |
| 2026-02-20 | SC/FR 171/25 | null | null `case_no`, no suspects |
| 2026-02-20 | LTA/17/2026 | null | null `case_no`, no suspects |
| 2026-02-20 | CA/HCC 177/2025, CA/LTA 17/2024 | null | null `case_no`, no suspects |

Note `CA/CPA 03/2026` on 2026-02-19 is the same matter as `CA/CPA/03/2026` from the
previous week's PDF, extracted with a different separator and into a different field.
Whatever ingestion path is chosen must normalise the identifier before deduplicating.

### Options

1. **Leave as-is.** The dashboard tracks prosecutions with named suspects; appellate
   petitions against the Commission are out of scope. Cheapest, and the review JSON
   preserves the data. Cost: the calendar is silently incomplete, and every week
   generates a review file that a human learns to ignore — which is how the regex
   bug in section A went unnoticed for five weeks.
2. **Add a second record type.** A `proceedings` table keyed on the appellate
   identifier, with `suspects` and `file_nos` optional. Route rows through a
   permissive branch when the case number matches `SC|CA|LTA|HC/TAB`. Correct, but
   it touches the schema, the API, and the dashboard.
3. **Relax the validators and let nulls through.** Not recommended — it removes the
   only signal distinguishing an appellate row from a genuinely botched extraction.

Option 2 is the right call if the calendar is meant to be complete. If it is not,
say so explicitly in the README so the review files stop looking like a backlog.

### Decision 2026-07-29: deferred, no owner

Neither option 1 nor option 2 was adopted. The scope question — is the CIABOC
calendar meant to be complete, or only the prosecutions with named suspects? — has
not been answered, and option 2 cannot be specified until it is: the schema, the
API surface, and the dashboard view all follow from that answer.

What this means in practice:

- The 24 rows stay rejected and stay in `data/processed/review/`. Nothing is lost;
  nothing is queryable either.
- The README makes **no** scope claim about appellate matters, because deferring is
  not the same as ruling them out. Do not add one until the question is settled.
- The review queue therefore keeps generating rows a human is expected to ignore —
  the exact condition that hid the section A bug for five weeks. The tests added on
  2026-07-29 remove the sharpest edge of that risk (a regex regression now fails
  loudly instead of silently), but they do not detect a *new* category of row.

Blocking on: a scope decision from whoever owns the project's editorial line.
Revisit when the appellate rows are either wanted in the dashboard or declared out
of scope in writing.

---

## Recommended order

1. ~~Patch `FILE_NO_PATTERN` and recover the four rows.~~ Done 2026-07-28.
2. ~~Add a regression test asserting `BC/C/1133/2016` and `BC/O/1203/2016` match and
   `SC/SPL/LA 182/2025` does not.~~ Done 2026-07-29. The repo had no test suite, so
   one was stood up: `tests/` with `pytest.ini`, 48 tests, no API key or database
   required.

   | File | Covers |
   |---|---|
   | `tests/test_file_no_pattern.py` | `FILE_NO_PATTERN` — sub-coded and plain forms match, appellate identifiers do not |
   | `tests/test_validate_cases.py` | the good/rejected split, one test per rejection reason in this report |
   | `tests/test_hearing_dates.py` | `pdf_date_window()` and `repair_hearing_dates()` — year drift corrected, real date errors left to be rejected |

   Run with `py -3 -m pytest`. Still missing: CI. Nothing runs these automatically.
3. ~~Decide on option 1 vs 2 for the appellate rows and record the decision.~~
   Recorded 2026-07-29 — [deferred](#decision-2026-07-29-deferred-no-owner), blocked
   on a scope call. Still open as a *question*; closed as an *action item*.
4. ~~Delete the redundant `.bak` files, or add `*.bak` to `.gitignore`.~~ Done
   2026-07-29 via `.gitignore`, which is the reversible half of that choice:
   - Added `data/processed/*.db.*`, which covers `.bak`, `.predatefix`, and
     `.pre-regexfix`. `*.bak` was already ignored.
   - `data/processed/ciaboc.db.bak` and `review_f8b6b836.json.bak` were **tracked**,
     so `.gitignore` alone did nothing for them. Both were untracked with
     `git rm --cached`; the files remain on disk.
   - The `.bak` files were not deleted from disk. They are byte-identical copies and
     safe to remove by hand, but that is a local call, not a repo change.

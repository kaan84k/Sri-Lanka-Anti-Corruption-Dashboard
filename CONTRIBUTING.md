# Contributing

Thanks for your interest in the **Sri Lanka Anti-Corruption Case Tracker**! This is a civic-tech,
public-interest project and contributions of every size are welcome.

## Code of conduct
Be respectful, assume good faith, and remember this project handles public-interest data about real
people. Harassment or bad-faith edits to the data are not tolerated.

## Getting set up
See the [Getting started](README.md#-getting-started) section of the README. You only need to set up
the component you plan to work on:

- **Pipeline** — Python 3.11+, `pip install google-genai pydantic pdfplumber`, a `GEMINI_API_KEY`.
- **API** — Python 3.11+, `pip install fastapi uvicorn`.
- **Dashboard** — Node 18+, `cd dashboard && npm install`.
- **Tests** — `pip install pytest`, then `py -3 -m pytest` from the repository root. No API key needed.

You can run the **API and dashboard without a Gemini key** using the existing database.

## Workflow
1. Fork the repository.
2. Create a branch: `git checkout -b feat/short-description` (or `fix/…`, `docs/…`).
3. Make focused commits with clear messages.
4. Run/verify the affected component (`py -3 -m pytest` for the pipeline; `npm run build` for the
   dashboard; start the API and hit `/docs`).
5. Open a Pull Request explaining **what** changed and **why**. Add screenshots for UI changes.

## What we're looking for
- **Extraction accuracy** — new PDF-layout edge cases, validation rules, court/identity fixes.
- **Dashboard** — visualizations, accessibility, mobile, Sinhala/Tamil i18n.
- **API** — endpoints, pagination, tests, performance.
- **Data quality** — clearing the `data/processed/review/` queue, verifying court levels and aliases.
- **Docs, design, CI** — always appreciated.

Look for issues labeled **`good first issue`** to start. See the
[Contributing section of the README](README.md#contributing) for the full list of focus areas.

## Ground rules
- Keep PRs small and focused — easier to review, faster to merge.
- Preserve the existing (deliberately heavy) code comments.
- **Never commit** secrets/API keys, or personal data beyond what the public CIABOC lists contain.
- Regenerate or update `data/processed/` only through the documented scripts, never by hand.

## Reporting issues
Open a GitHub issue with steps to reproduce, the PDF/date involved (if data-related), and expected vs
actual behavior. Data-accuracy reports are especially valuable — cite the source cause list.

Thank you for helping keep Sri Lankan anti-corruption data open and accurate.

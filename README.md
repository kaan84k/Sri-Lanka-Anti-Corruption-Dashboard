# Sri Lanka Anti-Corruption Dashboard

An in-progress project for collecting and presenting Sri Lankan anti-corruption data.

## Current contents

- A Python scraper for weekly CIABOC court-list PDFs
- Downloaded CIABOC source documents
- Project directories for the API, dashboard, data processing, and notebooks

## Downloading CIABOC documents

```powershell
python scraper/download_ciaboc_pdfs.py
```

The scraper downloads available weekly PDFs into `docs/` and records unavailable
weeks in `docs/missing_weeks.txt`.

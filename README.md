# Sri Lanka Anti-Corruption Dashboard

An in-progress project for collecting and presenting Sri Lankan anti-corruption data.

## Project structure

```text
data/
├── raw/                  # Immutable PDFs downloaded from CIABOC
└── processed/
    ├── ciaboc.db         # SQLite database created by the pipeline
    └── review/           # Rejected rows requiring manual review
scraper/                  # Downloads PDFs into data/raw/
pipeline/                 # Extracts and validates PDF data
api/                      # Serves data from ciaboc.db as JSON
dashboard/                # Frontend; communicates only with the API
notebooks/                # Exploration using the same ciaboc.db
docs/                     # Project documentation
```

## Downloading CIABOC documents

```powershell
py -3 scraper/download_ciaboc_pdfs.py
```

The scraper downloads available weekly PDFs into `data/raw/` and records
unavailable weeks in `data/raw/missing_weeks.txt`.

## Processing a PDF

Install the pipeline dependencies and set `GEMINI_API_KEY`, then run:

```powershell
py -3 pipeline/ciaboc_pipeline.py data/raw/20260112_-_20260116.pdf
```

Validated rows are saved in `data/processed/ciaboc.db`. Rejected rows are written
to `data/processed/review/` for manual checking.

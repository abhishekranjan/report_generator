# Report Generator

Self-serve report / newsletter generator for e-commerce crawl data. A client types what they want to know,
confirms a few details, and downloads a PDF.

```
prompt ──► Gemini picks the report type and extracts parameters
       ──► form: required fields (asked if missing) + optional fields
       ──► pandas computes every figure from the crawl data
       ──► Gemini writes the commentary around those figures
       ──► PDF (report or newsletter)
```

Gemini never produces numbers and never sees raw rows: it receives the list of valid options (to route the
request) and the aggregated figures (to write commentary). Without an API key the tool still works, using
keyword matching and template commentary.

## Report types

Each one is built on one crawl dataset. Files are recognised by their columns, not their names.

| Report type | Data | Required | Optional |
|---|---|---|---|
| Brand Shelf Health | Blinkit brand-page crawl | Brand | Sub-brands, pincodes |
| Category Landscape | Blinkit category-listing crawl | Category | Focus brand, cities |
| Amazon Bestseller Pulse | Amazon bestseller lists | Country | Categories |
| Search Visibility Tracker | Amazon search-results (SERP) crawl | Product | Keywords |
| Store-Level Availability | Blinkit product-page crawl | Product | Cities |

Every report also needs **Prepared for** and **Format** (report or newsletter); title, tone, rows per table
and accent colour are optional.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # then put your Gemini key in .env
```

`.env` holds the Gemini API key and is git-ignored. Never commit it.

### Load data

```bash
python -m app.ingest "C:\path\Brand Page.csv" "C:\path\SERP.csv" ...
```

This strips blank padding rows and empty columns and saves compact copies in `data/` (git-ignored).
Re-run it whenever you get a new export; the app picks up changes without a restart.

### Run

```bash
python run.py
```

Open http://127.0.0.1:8000.

## Project layout

```
app/
  data.py        load, recognise and clean the crawl CSVs
  ingest.py      import raw exports into data/
  modules/       one file per report type (fields + all calculations)
  llm.py         Gemini: prompt -> plan, figures -> commentary (+ fallbacks)
  charts.py      matplotlib chart rendering
  pdf.py         PDF layout (ReportLab)
  service.py     orchestration
  main.py        FastAPI endpoints
  static/        the web page
```

To add a report type, add a module in `app/modules/` exposing `ID, NAME, DATASET, DESCRIPTION, KEYWORDS,
ENTITY_FIELD, fields(df), build(df, params)` and register it in `app/modules/__init__.py`.

## Notes

- Figures describe what was visible on the platform at crawl time (listings, stock flags, prices, ranks) – not sales.
- City names are derived from store coordinates (nearest major city).
- The app binds to 127.0.0.1 and has no login. Put it behind authentication before exposing it to clients over a network.

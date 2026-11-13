# Report Generator

Self-serve report / newsletter generator for e-commerce crawl data. A client types what they want to know,
confirms a few details, and downloads a PDF.

Two ways in:

```
Talk to AI    describe ──► AI checks the request against the data, asks only what is missing
                       ──► choose AI-designed layout or a predefined template (with preview)
                       ──► confirm details ──► PDF

Use Filters   pick a report template (with preview) ──► set filters ──► PDF
```

Behind both: pandas computes every figure from the crawl data, Gemini writes the commentary (and, for
AI-designed reports, picks which analyses to show, their order and headings).

- Requests the data cannot serve (a brand, category, channel or metric that is not there) are refused with an
  explanation and alternatives – nothing is substituted silently.
- Filters: brand, sub-brand, category, competitors, city, pincode, product/SKU, keyword, country, rank range,
  date range (presets or custom) and which analyses to include. Each report shows only the filters its data supports.
- Templates live in `app/modules/__init__.py` (`TEMPLATES`); the assistant's rules are in `app/assistant.py`.

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

Presentation settings (prepared for, report or newsletter format, title, tone, rows per table, accent colour)
are all optional.

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
  assistant.py   the conversational requirement-gathering assistant
  llm.py         Gemini calls, option validation, commentary and AI layout (+ fallbacks)
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

"""Registry of report modules. Add a module here to add a report type."""
from .. import data
from . import bestsellers, brand, category, serp, store

ALL = {m.ID: m for m in (brand, category, bestsellers, serp, store)}

FORMATS = [{"value": "report", "label": "Report (detailed, multi-page)"},
           {"value": "newsletter", "label": "Newsletter (short, headline-led)"}]
TONES = [{"value": "executive", "label": "Executive – crisp, decision-led"},
         {"value": "analytical", "label": "Analytical – detailed, neutral"},
         {"value": "friendly", "label": "Friendly – conversational"}]


def available():
    """Modules whose dataset is present in the data folder."""
    frames = data.load_all()
    return {mid: m for mid, m in ALL.items() if m.DATASET in frames and len(frames[m.DATASET])}


def common_fields():
    """Fields every report needs, whatever the module."""
    return [
        {"key": "client_name", "label": "Prepared for", "type": "text", "required": True,
         "help": "Client or team name shown on the cover."},
        {"key": "format", "label": "Format", "type": "select", "required": True, "options": FORMATS, "default": "report",
         "help": "A full report or a short newsletter."},
        {"key": "title", "label": "Report title", "type": "text", "required": False,
         "help": "Leave empty to have one written for you."},
        {"key": "tone", "label": "Tone", "type": "select", "required": False, "options": TONES, "default": "executive",
         "help": "Writing style of the commentary."},
        {"key": "top_n", "label": "Rows per table / chart", "type": "number", "required": False, "default": 10,
         "help": "Between 3 and 25."},
        {"key": "accent", "label": "Accent colour", "type": "color", "required": False, "default": "#1c5cab",
         "help": "Used for the cover and headings."},
    ]


def module_fields(mid):
    m = ALL[mid]
    return m.fields(data.get(m.DATASET))


def catalog():
    """Everything the UI and the planner need to know about what can be built."""
    out = []
    for mid, m in available().items():
        df = data.get(m.DATASET)
        out.append({"id": mid, "name": m.NAME, "description": m.DESCRIPTION,
                    "source": data.DATASET_LABELS[m.DATASET], "rows": len(df), "dates": data.date_span(df),
                    "fields": m.fields(df)})
    return out

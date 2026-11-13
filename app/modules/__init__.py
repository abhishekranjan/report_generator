"""Registry of report modules and predefined templates.

A module = one dataset + its calculations. A template = a named, fixed selection
of a module's analyses. Add a module or a template here to make it available.
"""
from .. import data
from . import bestsellers, brand, category, serp, store

ALL = {m.ID: m for m in (brand, category, bestsellers, serp, store)}

# sections=None means "every analysis the module has". requires = optional fields this template makes mandatory.
TEMPLATES = [
    {"id": "brand_shelf_health", "module": "brand_shelf", "name": "Brand Shelf Health",
     "description": "Full health check of one brand on Blinkit: range, availability, stock-outs, pricing and shelf position.",
     "sections": None},
    {"id": "product_availability", "module": "brand_shelf", "name": "Product Availability Report",
     "description": "Where a brand's products are in and out of stock, by pincode and by SKU.",
     "sections": ["pincode_availability", "oos_hotspots", "shelf_position"]},
    {"id": "pricing_discount", "module": "brand_shelf", "name": "Pricing and Discount Analysis",
     "description": "Discount depth, deepest-discounted SKUs and price consistency across stores for one brand.",
     "sections": ["pricing", "portfolio"]},
    {"id": "category_performance", "module": "category_landscape", "name": "Category Performance",
     "description": "Who leads a Blinkit category: share of shelf, ads, price bands, availability and top products.",
     "sections": ["share_of_shelf", "sponsored", "pricing", "city_availability", "top_products"]},
    {"id": "competitor_benchmarking", "module": "category_landscape", "name": "Competitor Benchmarking",
     "description": "One brand against its category rivals: share of shelf, ad presence, availability and a head-to-head scorecard.",
     "sections": ["focus_brand", "share_of_shelf", "sponsored", "city_availability"], "requires": ["focus_brand"]},
    {"id": "bestseller_pulse", "module": "bestsellers", "name": "Amazon Bestseller Pulse",
     "description": "What is winning on Amazon bestseller lists in one country, and which newcomers are breaking in.",
     "sections": None},
    {"id": "search_visibility", "module": "keyword_visibility", "name": "Search Visibility Report",
     "description": "How a product ranks in Amazon search by keyword: organic vs sponsored, trend and price tracking.",
     "sections": None},
    {"id": "store_availability", "module": "store_availability", "name": "Store-Level Availability",
     "description": "Store-by-store availability of a single product on Blinkit, with city coverage and price points.",
     "sections": None},
]
TEMPLATE_BY_ID = {t["id"]: t for t in TEMPLATES}

FORMATS = [{"value": "report", "label": "Report (detailed, multi-page)"},
           {"value": "newsletter", "label": "Newsletter (short, headline-led)"}]
TONES = [{"value": "executive", "label": "Executive – crisp, decision-led"},
         {"value": "analytical", "label": "Analytical – detailed, neutral"},
         {"value": "friendly", "label": "Friendly – conversational"}]


def available():
    """Modules whose dataset is present in the data folder."""
    frames = data.load_all()
    return {mid: m for mid, m in ALL.items() if m.DATASET in frames and len(frames[m.DATASET])}


def templates():
    av = available()
    return [t for t in TEMPLATES if t["module"] in av]


def common_fields():
    """Presentation settings – none of them is mandatory."""
    return [
        {"key": "client_name", "label": "Prepared for", "type": "text", "required": False,
         "help": "Client or team name shown on the cover (optional)."},
        {"key": "format", "label": "Format", "type": "select", "required": False, "options": FORMATS, "default": "report",
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


def module_fields(mid, template_id=None):
    """The module's own filters plus the two generic ones (date range, analyses)."""
    m = ALL[mid]
    df = data.get(m.DATASET)
    fs = [dict(f) for f in m.fields(df)]
    lo, hi = data.date_bounds(df)
    fs.append({"key": "date_range", "label": "Date range", "type": "daterange", "required": False,
               "min": lo, "max": hi, "help": f"Data available: {data.date_span(df)}."})
    t = TEMPLATE_BY_ID.get(template_id) if template_id else None
    secs = [s for s in m.SECTIONS if not t or t["sections"] is None or s[0] in t["sections"]]
    fs.append({"key": "sections", "label": "Metrics / analyses to include", "type": "multi", "required": False,
               "options": [{"value": s[0], "label": s[1]} for s in secs],
               "help": "Leave empty to include everything in the chosen design."})
    if t:
        for f in fs:
            if f["key"] in t.get("requires", []):
                f["required"] = True
                f["help"] = "Needed for this template."
    return fs


def catalog():
    """Everything the UI and the assistant need to know about what can be built."""
    out = []
    for mid, m in available().items():
        df = data.get(m.DATASET)
        out.append({"id": mid, "name": m.NAME, "description": m.DESCRIPTION, "channel": m.CHANNEL,
                    "source": data.DATASET_LABELS[m.DATASET], "rows": len(df), "dates": data.date_span(df),
                    "sections": [{"id": s[0], "title": s[1], "shows": s[2]} for s in m.SECTIONS],
                    "templates": [{"id": t["id"], "name": t["name"]} for t in TEMPLATES if t["module"] == mid],
                    "fields": module_fields(mid)})
    return out

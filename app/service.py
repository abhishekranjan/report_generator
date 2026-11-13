"""Orchestration: prompt -> plan -> (confirm fields) -> compute -> narrate -> PDF."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from . import config, data, llm, modules, pdf

EXAMPLES = [
    "How is Britannia doing on Blinkit? I want availability by pincode and the worst out-of-stock SKUs.",
    "Give me a competitive landscape of the Bread category and benchmark Harvest Gold against it.",
    "Weekly newsletter on Amazon bestsellers in Mexico – what is winning and who are the new challengers?",
    "How does Ghar Soaps rank in Amazon search for soap keywords? Organic vs sponsored and the trend.",
    "Where is the Lakme 9to5 foundation actually in stock across Blinkit stores?",
]


def _fields_for(mid):
    return modules.module_fields(mid) + modules.common_fields()


def _missing(fields, values):
    return [f["key"] for f in fields if f["required"] and values.get(f["key"]) in (None, "", [])]


def overview():
    cat = modules.catalog()
    return {"modules": [{k: m[k] for k in ("id", "name", "description", "source", "rows", "dates")} for m in cat],
            "examples": EXAMPLES, "gemini": config.gemini_enabled(), "model": config.GEMINI_MODEL,
            "company": config.COMPANY_NAME}


def make_plan(prompt: str) -> dict:
    cat = modules.catalog()
    if not cat:
        raise ValueError("No data found. Import crawl CSVs first: python -m app.ingest <files>")
    common = modules.common_fields()
    kw = {mid: m.KEYWORDS for mid, m in modules.ALL.items()}
    ent = {mid: m.ENTITY_FIELD for mid, m in modules.ALL.items()}
    plan = llm.plan(prompt, cat, common, kw, ent)
    for f in common:  # defaults for anything not stated
        if "default" in f:
            plan["values"].setdefault(f["key"], f["default"])
    mid = plan["module"]
    fields = _fields_for(mid) if mid else []
    plan.update(fields=fields, missing=_missing(fields, plan["values"]) if mid else ["module"])
    return plan


def fields(mid: str) -> dict:
    if mid not in modules.available():
        raise ValueError("Unknown report type.")
    fs = _fields_for(mid)
    values = {f["key"]: f["default"] for f in fs if "default" in f}
    for f in fs:  # a required choice with a single option answers itself
        if f["type"] == "select" and f["required"] and len(f.get("options", [])) == 1:
            values[f["key"]] = f["options"][0]["value"]
    return {"fields": fs, "values": values}


def generate(prompt: str, mid: str, values: dict) -> dict:
    avail = modules.available()
    if mid not in avail:
        raise ValueError("Unknown report type.")
    m = avail[mid]
    fs = _fields_for(mid)
    # re-validate everything server-side: never trust the form
    clean = llm.normalise({"module": mid, "params": values, **{f["key"]: values.get(f["key"]) for f in modules.common_fields()}},
                          modules.catalog(), modules.common_fields())["values"]
    for f in fs:
        if "default" in f:
            clean.setdefault(f["key"], f["default"])
    miss = _missing(fs, clean)
    if miss:
        labels = {f["key"]: f["label"] for f in fs}
        raise ValueError("Please fill in: " + ", ".join(labels[k] for k in miss))

    df = data.get(m.DATASET)
    report = m.build(df, clean)
    meta = {"module_name": m.NAME, "prompt": prompt.strip(), "tone": clean.get("tone", "executive"),
            "format": clean.get("format", "report"), "title": clean.get("title"), "client_name": clean["client_name"],
            "accent": clean.get("accent"), "source_label": data.DATASET_LABELS[m.DATASET], "dates": data.date_span(df),
            "generated": datetime.now()}
    narrative = llm.narrate(report, meta)

    rid = uuid.uuid4().hex
    slug = re.sub(r"[^a-z0-9]+", "-", f"{clean['client_name']} {m.NAME} {report['subject']}".lower()).strip("-")[:70]
    filename = f"{slug}-{meta['generated']:%Y%m%d}.pdf"
    path = config.OUTPUT_DIR / f"{rid}.pdf"
    pages = pdf.build_pdf(path, report, narrative, meta)
    (config.OUTPUT_DIR / f"{rid}.name").write_text(filename, encoding="utf-8")
    return {"id": rid, "filename": filename, "title": narrative["title"], "headline": narrative["headline"],
            "pages": pages, "narrative_source": narrative["source"], "model": narrative.get("model"), "warning": narrative.get("warning"),
            "url": f"/api/reports/{rid}"}

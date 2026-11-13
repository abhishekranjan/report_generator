"""Orchestration: conversation or filters -> design -> confirm -> compute -> narrate -> PDF."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime

from . import assistant, config, data, llm, modules, pdf

EXAMPLES = [
    "Generate a health score report for Britannia.",
    "Compare Harvest Gold against its competitors in the Bread category.",
    "What is winning on Amazon bestsellers in Mexico, and who are the new challengers?",
    "How does Ghar Soaps rank in Amazon search? Organic vs sponsored and the trend.",
    "Where is the Lakme 9to5 foundation actually in stock across Blinkit stores?",
]
PREVIEW_DIR = config.OUTPUT_DIR / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------- helpers
def _kw():
    return {mid: m.KEYWORDS for mid, m in modules.ALL.items()}, {mid: m.ENTITY_FIELD for mid, m in modules.ALL.items()}


def _fields_for(mid, template_id=None):
    return modules.module_fields(mid, template_id) + modules.common_fields()


def _missing(fields, values):
    return [f["key"] for f in fields if f["required"] and values.get(f["key"]) in (None, "", [])]


def _opts(f, values):
    o = f.get("options") or []
    if f.get("depends_on"):
        o = [x for x in o if x.get("parent") in (None, values.get(f["depends_on"]))]
    return o


def _design(design):
    """Normalise the design choice: AI-designed, or a predefined template."""
    design = design or {}
    t = modules.TEMPLATE_BY_ID.get(design.get("template"))
    if design.get("mode") == "template" and t:
        return {"mode": "template", "template": t["id"]}
    return {"mode": "ai", "template": None}


def _date_label(v):
    if not v or v.get("preset", "all") == "all":
        return ""
    if v["preset"] == "custom":
        return f"{v.get('from') or 'start'} to {v.get('to') or 'latest'}"
    return f"Last {v['preset']} days"


def summary(mid, values):
    """Readable 'what I understood' rows for the chat summary card and the confirm screen."""
    if mid not in modules.available():
        return []
    m = modules.ALL[mid]
    df = data.get(m.DATASET)
    rows = [{"label": "Report type", "value": m.NAME}, {"label": "Channel", "value": m.CHANNEL}]
    for f in modules.module_fields(mid):
        v = values.get(f["key"])
        if f["type"] == "daterange":
            rows.append({"label": "Date range", "value": _date_label(v) or f"All available data ({data.date_span(df)})"})
            continue
        if v in (None, "", []):
            if not f["required"] and f["key"] != "sections":
                rows.append({"label": f["label"], "value": "All", "muted": True})
            continue
        labels = {o["value"]: o["label"] for o in f.get("options", [])}
        vs = v if isinstance(v, list) else [v]
        rows.append({"label": f["label"], "value": ", ".join(labels.get(x, str(x)) for x in vs)})
    return rows


def overview():
    cat = modules.catalog()
    by_id = {m["id"]: m for m in cat}
    tpls = []
    for t in modules.templates():
        m = by_id[t["module"]]
        secs = [s["title"] for s in m["sections"] if t["sections"] is None or s["id"] in t["sections"]]
        tpls.append({"id": t["id"], "name": t["name"], "module": t["module"], "description": t["description"],
                     "channel": m["channel"], "sections": secs, "dates": m["dates"]})
    return {"modules": [{k: m[k] for k in ("id", "name", "description", "channel", "source", "rows", "dates", "sections")} for m in cat],
            "templates": tpls, "channels": sorted({m["channel"] for m in cat}), "examples": EXAMPLES,
            "gemini": config.gemini_enabled(), "model": config.GEMINI_MODEL, "company": config.COMPANY_NAME}


# ----------------------------------------------------------------- conversation
def chat(messages: list, state: dict) -> dict:
    cat = modules.catalog()
    if not cat:
        raise ValueError("No data found. Import crawl CSVs first: python -m app.ingest <files>")
    msgs = [{"role": "assistant" if m.get("role") == "assistant" else "user", "text": str(m.get("text", ""))[:2000]}
            for m in messages if str(m.get("text", "")).strip()][-20:]
    if not msgs or msgs[-1]["role"] != "user":
        raise ValueError("Tell me what the report should cover.")
    kw, ent = _kw()
    res = assistant.chat(msgs, state or {}, cat, modules.common_fields(), kw, ent)
    # things the data cannot provide stay flagged for the rest of the conversation
    prior = [str(x)[:60] for x in (state or {}).get("unsupported") or []]
    res["unsupported"] = list(dict.fromkeys(prior + res["unsupported"]))[:8]
    res["summary"] = summary(res["module"], res["values"]) if res["module"] else []
    res["templates"] = [t["id"] for t in modules.templates() if t["module"] == res["module"]]
    return res


def fields(mid: str, template_id: str | None = None) -> dict:
    if mid not in modules.available():
        raise ValueError("Unknown report type.")
    fs = _fields_for(mid, template_id)
    values = {f["key"]: f["default"] for f in fs if "default" in f}
    for f in fs:  # a required choice with a single option answers itself
        if f["type"] == "select" and f["required"] and len(f.get("options", [])) == 1:
            values[f["key"]] = f["options"][0]["value"]
    return {"fields": fs, "values": values}


# ----------------------------------------------------------------- building
def _assemble(prompt, mid, values, design, unsupported=None, use_llm=True, sample=False):
    avail = modules.available()
    if mid not in avail:
        raise ValueError("Unknown report type.")
    m = avail[mid]
    design = _design(design)
    tpl = modules.TEMPLATE_BY_ID.get(design["template"])
    if tpl and tpl["module"] != mid:
        raise ValueError("That template belongs to a different report type.")
    fs = _fields_for(mid, design["template"])
    common = modules.common_fields()
    # re-validate everything server-side: never trust the form
    clean = llm.normalise({"module": mid, "params": values, **{f["key"]: values.get(f["key"]) for f in common}},
                          modules.catalog(), common)["values"]
    for f in fs:
        if "default" in f:
            clean.setdefault(f["key"], f["default"])
    used_sample = False
    if sample:  # previews fall back to the first available option so a layout can always be shown
        for f in fs:
            if f["required"] and clean.get(f["key"]) in (None, "", []) and _opts(f, clean):
                clean[f["key"]] = _opts(f, clean)[0]["value"]
                used_sample = True
    miss = _missing(fs, clean)
    if miss:
        labels = {f["key"]: f["label"] for f in fs}
        raise ValueError("Please fill in: " + ", ".join(labels[k] for k in miss))

    df = data.get(m.DATASET)
    scoped, date_note = data.filter_dates(df, clean.get("date_range"))
    report = m.build(scoped, clean)
    if date_note:
        report["scope"] = date_note + ("; " + report["scope"] if report["scope"] else "")

    # which analyses go in: explicit pick > template > everything (AI may narrow further)
    wanted = clean.get("sections") or (tpl["sections"] if tpl else None)
    if wanted:
        by = {s["id"]: s for s in report["sections"]}
        picked = [by[i] for i in wanted if i in by]
        if picked:
            report["sections"] = picked
    meta = {"module_name": tpl["name"] if tpl else m.NAME, "prompt": (prompt or "").strip(), "tone": clean.get("tone", "executive"),
            "format": clean.get("format", "report"), "title": clean.get("title"), "client_name": clean.get("client_name", ""),
            "accent": clean.get("accent"), "source_label": data.DATASET_LABELS[m.DATASET], "dates": data.date_span(scoped),
            "generated": datetime.now(), "design_mode": "ai" if design["mode"] == "ai" and not clean.get("sections") else "fixed",
            "design_label": f"Predefined template: {tpl['name']}" if tpl else "AI-designed custom layout",
            "unsupported": [str(u)[:60] for u in (unsupported or [])][:6], "use_llm": use_llm, "preview": sample}
    narrative = llm.narrate(report, meta)

    lay = narrative.get("layout")
    if lay:  # apply the AI's layout: order/selection of sections and headline metrics, plus its headings
        by = {s["id"]: s for s in report["sections"]}
        report["sections"] = [by[i] for i in lay["sections"] if i in by]
        if lay.get("kpis"):
            kb = {k["label"]: k for k in report["kpis"]}
            report["kpis"] = [kb[l] for l in lay["kpis"] if l in kb]
    for s in report["sections"]:
        s["title"] = narrative.get("section_titles", {}).get(s["id"], s["title"])
    return m, report, narrative, meta, clean, used_sample


def generate(prompt: str, mid: str, values: dict, design: dict | None = None, unsupported: list | None = None) -> dict:
    m, report, narrative, meta, clean, _ = _assemble(prompt, mid, values, design, unsupported)
    rid = uuid.uuid4().hex
    slug = re.sub(r"[^a-z0-9]+", "-", f"{clean.get('client_name', '')} {meta['module_name']} {report['subject']}".lower()).strip("-")[:70]
    filename = f"{slug}-{meta['generated']:%Y%m%d}.pdf"
    path = config.OUTPUT_DIR / f"{rid}.pdf"
    pages = pdf.build_pdf(path, report, narrative, meta)
    (config.OUTPUT_DIR / f"{rid}.name").write_text(filename, encoding="utf-8")
    return {"id": rid, "filename": filename, "title": narrative["title"], "headline": narrative["headline"],
            "pages": pages, "narrative_source": narrative["source"], "model": narrative.get("model"),
            "warning": narrative.get("warning"), "design": meta["design_label"],
            "sections": [s["title"] for s in report["sections"]], "url": f"/api/reports/{rid}"}


def preview(mid: str, values: dict, design: dict | None = None) -> dict:
    """Fast layout preview: real figures, placeholder commentary, first pages as images. No AI call."""
    import pypdfium2 as pdfium

    key = hashlib.sha1(json.dumps([mid, values, _design(design), data._scan()], sort_keys=True, default=str).encode()).hexdigest()[:20]
    meta_file = PREVIEW_DIR / f"{key}.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text(encoding="utf-8"))
    m, report, narrative, meta, clean, used_sample = _assemble("", mid, values, design, use_llm=False, sample=True)
    path = PREVIEW_DIR / f"{key}.pdf"
    total = pdf.build_pdf(path, report, narrative, meta)
    doc = pdfium.PdfDocument(str(path))
    pages = []
    for i in range(min(3, len(doc))):
        doc[i].render(scale=1.1).to_pil().save(PREVIEW_DIR / f"{key}_{i + 1}.png", optimize=True)
        pages.append(f"/api/previews/{key}_{i + 1}.png")
    doc.close()
    path.unlink(missing_ok=True)
    out = {"pages": pages, "total_pages": total, "design": meta["design_label"], "subject": report["subject"],
           "sample": used_sample, "sections": [s["title"] for s in report["sections"]],
           "kpis": [k["label"] for k in report["kpis"]],
           "ai_note": meta["design_mode"] == "ai"}
    meta_file.write_text(json.dumps(out), encoding="utf-8")
    return out

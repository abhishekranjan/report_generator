"""Web app. Run with:  python run.py   (or: uvicorn app.main:app)"""
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import config, service

app = FastAPI(title="Report Generator", docs_url=None, redoc_url=None)
STATIC = Path(__file__).parent / "static"


class PlanIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


class GenerateIn(BaseModel):
    prompt: str = Field(default="", max_length=2000)
    module: str = Field(max_length=60)
    values: dict


def _guard(fn, *a):
    try:
        return fn(*a)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/overview")
def overview():
    return service.overview()


@app.post("/api/plan")
def plan(body: PlanIn):
    return _guard(service.make_plan, body.prompt)


@app.get("/api/fields")
def fields(module: str):
    return _guard(service.fields, module)


@app.post("/api/generate")
def generate(body: GenerateIn):
    return _guard(service.generate, body.prompt, body.module, body.values)


@app.get("/api/reports/{rid}")
def report(rid: str, download: int = 0):
    if not re.fullmatch(r"[0-9a-f]{32}", rid):
        raise HTTPException(status_code=404)
    path = config.OUTPUT_DIR / f"{rid}.pdf"
    if not path.exists():
        raise HTTPException(status_code=404)
    name_file = config.OUTPUT_DIR / f"{rid}.name"
    name = name_file.read_text(encoding="utf-8") if name_file.exists() else "report.pdf"
    return FileResponse(path, media_type="application/pdf", filename=name,
                        content_disposition_type="attachment" if download else "inline")

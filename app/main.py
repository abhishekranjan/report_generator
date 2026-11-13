"""Web app. Run with:  python run.py   (or: uvicorn app.main:app)"""
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import config, service

app = FastAPI(title="Report Generator", docs_url=None, redoc_url=None)
STATIC = Path(__file__).parent / "static"


class Message(BaseModel):
    role: str = Field(max_length=12)
    text: str = Field(max_length=2000)


class ChatIn(BaseModel):
    messages: list[Message] = Field(max_length=40)
    state: dict = {}


class BuildIn(BaseModel):
    prompt: str = Field(default="", max_length=6000)
    module: str = Field(max_length=60)
    values: dict = {}
    design: dict = {}
    unsupported: list[str] = Field(default=[], max_length=10)


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


@app.post("/api/chat")
def chat(body: ChatIn):
    return _guard(service.chat, [m.model_dump() for m in body.messages], body.state)


@app.get("/api/fields")
def fields(module: str, template: str | None = None):
    return _guard(service.fields, module, template)


@app.post("/api/preview")
def preview(body: BuildIn):
    return _guard(service.preview, body.module, body.values, body.design)


@app.post("/api/generate")
def generate(body: BuildIn):
    return _guard(service.generate, body.prompt, body.module, body.values, body.design, body.unsupported)


@app.get("/api/previews/{name}")
def preview_image(name: str):
    if not re.fullmatch(r"[0-9a-f]{20}_[1-3]\.png", name):
        raise HTTPException(status_code=404)
    path = service.PREVIEW_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png")


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

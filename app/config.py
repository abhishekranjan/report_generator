"""Central configuration. Secrets come from .env (never committed)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", ROOT / "output"))
COMPANY_NAME = os.getenv("COMPANY_NAME", "Digital Shelf Insights").strip()

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def gemini_enabled() -> bool:
    return bool(GEMINI_API_KEY) and GEMINI_API_KEY.lower() not in {"your_gemini_api_key_here", "changeme"}

"""Load, recognise and clean the crawl CSVs.

Files are recognised by their column signature (not their name), so any export
of the same crawl type dropped into DATA_DIR is picked up automatically.
"""
from __future__ import annotations

import math
import re
import threading

import numpy as np
import pandas as pd

from . import config

# dataset id -> columns that must all be present
SIGNATURES = {
    "brand_page": {"Brand URL", "Pincode", "In Stock"},
    "category": {"Category URL", "Price Higher", "Availability"},
    "bestsellers": {"Category Page URL", "Listing Type", "Country Code"},
    "serp": {"Keyword", "Product Page URL", "Sponsored"},
    "product_details": {"Stock Status", "Source URL", "Manufacturer"},
}

DATASET_LABELS = {
    "brand_page": "Blinkit brand-page crawl",
    "category": "Blinkit category-listing crawl",
    "bestsellers": "Amazon bestseller-list crawl",
    "serp": "Amazon search-results (SERP) crawl",
    "product_details": "Blinkit product-page crawl (store level)",
}

COUNTRIES = {"MX": "Mexico", "AU": "Australia", "AE": "United Arab Emirates", "TR": "Turkey", "IN": "India",
             "US": "United States", "GB": "United Kingdom", "SA": "Saudi Arabia", "DE": "Germany"}

# (city, lat, lon) – used to turn store coordinates into a readable city.
CITIES = [
    ("Delhi", 28.61, 77.21), ("Gurugram", 28.46, 77.03), ("Noida", 28.54, 77.39), ("Ghaziabad", 28.67, 77.45),
    ("Faridabad", 28.41, 77.31), ("Mumbai", 19.08, 72.88), ("Thane", 19.22, 72.98), ("Navi Mumbai", 19.03, 73.03),
    ("Pune", 18.52, 73.86), ("Bengaluru", 12.97, 77.59), ("Hyderabad", 17.39, 78.49), ("Chennai", 13.08, 80.27),
    ("Kolkata", 22.57, 88.36), ("Ahmedabad", 23.02, 72.57), ("Surat", 21.17, 72.83), ("Vadodara", 22.31, 73.18),
    ("Jaipur", 26.91, 75.79), ("Lucknow", 26.85, 80.95), ("Kanpur", 26.45, 80.33), ("Chandigarh", 30.73, 76.78),
    ("Ludhiana", 30.90, 75.86), ("Amritsar", 31.63, 74.87), ("Jalandhar", 31.33, 75.58), ("Indore", 22.72, 75.86),
    ("Bhopal", 23.26, 77.41), ("Nagpur", 21.15, 79.09), ("Nashik", 20.00, 73.79), ("Kochi", 9.93, 76.27),
    ("Thiruvananthapuram", 8.52, 76.94), ("Coimbatore", 11.02, 76.96), ("Visakhapatnam", 17.69, 83.22),
    ("Vijayawada", 16.51, 80.65), ("Patna", 25.59, 85.14), ("Ranchi", 23.34, 85.31), ("Bhubaneswar", 20.30, 85.82),
    ("Guwahati", 26.14, 91.74), ("Dehradun", 30.32, 78.03), ("Meerut", 28.98, 77.71), ("Agra", 27.18, 78.01),
    ("Varanasi", 25.32, 82.97), ("Prayagraj", 25.44, 81.85), ("Rajkot", 22.30, 70.80), ("Goa", 15.40, 73.95),
    ("Mysuru", 12.30, 76.64), ("Mangaluru", 12.91, 74.86), ("Jodhpur", 26.24, 73.02), ("Udaipur", 24.58, 73.71),
    ("Raipur", 21.25, 81.63), ("Jammu", 32.73, 74.86), ("Haridwar", 29.95, 78.16), ("Gwalior", 26.22, 78.18),
    ("Kota", 25.18, 75.83), ("Aurangabad", 19.88, 75.34), ("Hubballi", 15.36, 75.12), ("Madurai", 9.93, 78.12),
    ("Jamshedpur", 22.80, 86.20), ("Siliguri", 26.73, 88.40), ("Bareilly", 28.37, 79.43), ("Moradabad", 28.84, 78.77),
    ("Rohtak", 28.90, 76.61), ("Panipat", 29.39, 76.97), ("Sonipat", 28.99, 77.02), ("Karnal", 29.69, 76.99),
    ("Ambala", 30.38, 76.78), ("Patiala", 30.34, 76.39), ("Bathinda", 30.21, 74.95), ("Hisar", 29.15, 75.72),
    ("Aligarh", 27.90, 78.09), ("Mathura", 27.49, 77.67), ("Gorakhpur", 26.76, 83.37), ("Ajmer", 26.45, 74.64),
    ("Jabalpur", 23.18, 79.99), ("Kolhapur", 16.70, 74.24), ("Belagavi", 15.85, 74.50), ("Tirupati", 13.63, 79.42),
    ("Guntur", 16.31, 80.44), ("Warangal", 17.97, 79.59), ("Salem", 11.66, 78.15), ("Tiruchirappalli", 10.79, 78.70),
    ("Puducherry", 11.94, 79.81), ("Kozhikode", 11.26, 75.78), ("Thrissur", 10.53, 76.21), ("Shimla", 31.10, 77.17),
    ("Bhilai", 21.19, 81.35), ("Cuttack", 20.46, 85.88), ("Durgapur", 23.52, 87.31), ("Anand", 22.56, 72.95),
    ("Bhavnagar", 21.76, 72.15), ("Jamnagar", 22.47, 70.06), ("Gandhinagar", 23.22, 72.65), ("Bikaner", 28.02, 73.31),
    ("Saharanpur", 29.97, 77.55), ("Jhansi", 25.45, 78.57), ("Ujjain", 23.18, 75.78), ("Solapur", 17.66, 75.91),
]
_CITY_ARR = np.array([[c[1], c[2]] for c in CITIES])

# Indian PIN prefix -> city (4-digit prefixes win over 3-digit ones).
PIN_CITY = {
    "110": "Delhi", "121": "Faridabad", "122": "Gurugram", "140": "Mohali", "141": "Ludhiana", "143": "Amritsar",
    "160": "Chandigarh", "2010": "Ghaziabad", "2013": "Noida", "201": "Ghaziabad", "208": "Kanpur", "226": "Lucknow",
    "282": "Agra", "302": "Jaipur", "360": "Rajkot", "380": "Ahmedabad", "382": "Ahmedabad", "390": "Vadodara",
    "395": "Surat", "400": "Mumbai", "401": "Mumbai region", "411": "Pune", "440": "Nagpur", "452": "Indore",
    "462": "Bhopal", "500": "Hyderabad", "530": "Visakhapatnam", "560": "Bengaluru", "600": "Chennai",
    "641": "Coimbatore", "682": "Kochi", "700": "Kolkata", "751": "Bhubaneswar", "781": "Guwahati", "800": "Patna",
}


def pin_city(pin) -> str:
    p = str(pin or "")
    return PIN_CITY.get(p[:4]) or PIN_CITY.get(p[:3]) or ""


_lock = threading.Lock()
_cache: dict = {"key": None, "frames": {}, "files": {}}


# ----------------------------------------------------------------- helpers
def num(s: pd.Series) -> pd.Series:
    """'3,019' / '46,800' / '' -> float."""
    out = pd.to_numeric(s.astype("string").str.replace(",", "", regex=False).str.strip(), errors="coerce")
    return out.astype("float64")  # plain floats with NaN – no pd.NA surprises downstream


def _fix_text(v):
    """Repair UTF-8 that was decoded as cp1252 ('BÃ¡lsamos' -> 'Bálsamos', 'â‚¹' -> '₹')."""
    if not isinstance(v, str) or v.isascii():
        return v
    try:
        return v.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return v


def fix_text(s: pd.Series) -> pd.Series:
    return s.map(_fix_text)


def to_dt(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, format="%B %d, %Y, %H:%M", errors="coerce")
    if out.isna().all():
        out = pd.to_datetime(s, format="%B %d, %Y", errors="coerce")
    return out


def truthy(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.lower().isin(["true", "1", "yes", "in stock", "instock"])


def nearest_city(lat: pd.Series, lon: pd.Series, max_km: float = 70) -> pd.Series:
    la, lo = lat.to_numpy(dtype=float), lon.to_numpy(dtype=float)
    out = np.full(len(la), "Unknown", dtype=object)
    ok = ~(np.isnan(la) | np.isnan(lo))
    if ok.any():
        dlat = (la[ok, None] - _CITY_ARR[None, :, 0]) * 111.0
        dlon = (lo[ok, None] - _CITY_ARR[None, :, 1]) * 111.0 * np.cos(np.radians(la[ok, None]))
        d = np.sqrt(dlat ** 2 + dlon ** 2)
        idx = d.argmin(axis=1)
        names = np.array([c[0] for c in CITIES], dtype=object)[idx]
        names[d.min(axis=1) > max_km] = "Other towns"
        out[ok] = names
    return pd.Series(out, index=lat.index)


def detect(columns) -> str | None:
    cols = set(columns)
    for ds, sig in SIGNATURES.items():
        if sig <= cols:
            return ds
    return None


def read_raw(path) -> pd.DataFrame:
    """Read a crawl CSV, dropping the blank padding rows Excel-style exports carry."""
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8", low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(path, dtype=str, encoding="cp1252", low_memory=False)
    return df.dropna(how="all")


# ----------------------------------------------------------------- cleaners
def _slug_name(url: str) -> str:
    m = re.search(r"/brand/([^/]+)", url or "")
    if not m:
        return "Unknown"
    return " ".join(w.upper() if w.isdigit() or len(w) <= 2 else w.capitalize() for w in m.group(1).split("-"))


def _clean_brand_page(df):
    o = pd.DataFrame(index=df.index)
    o["brand_family"] = df["Brand URL"].map(_slug_name)
    o["brand"] = df["Brand"].str.strip()
    o["sku"] = df["Sku"]
    o["title"] = fix_text(df["Title"]).str.strip()
    o["quantity"] = df["Quantity"]
    o["mrp"] = num(df["Mrp"])
    o["price"] = num(df["Price"])
    o["pincode"] = df["Pincode"].str.replace(",", "", regex=False)
    o["pin_city"] = o["pincode"].map(pin_city)
    o["store_id"] = df["Store ID"]
    o["rank"] = num(df["Rank"])
    o["page"] = num(df["Page Number"])
    o["position"] = (o["page"] - 1) * o.groupby(["brand_family"])["rank"].transform("max") + o["rank"]
    o["in_stock"] = truthy(df["In Stock"])
    o["stock"] = num(df["Stock"])
    o["rating"] = num(df["Rating"])
    o["crawl_date"] = to_dt(df["Crawl Date"])
    o["discount"] = np.where((o["mrp"] > 0) & (o["price"] > 0), (o["mrp"] - o["price"]) / o["mrp"] * 100, np.nan)
    o["discount"] = o["discount"].clip(lower=0)
    return o


def _clean_category(df):
    o = pd.DataFrame(index=df.index)
    cat = df["Category"].str.strip()
    # some rows miss the category name – recover it from the category id
    by_id = cat.groupby(df["Category ID"]).agg(lambda s: s.dropna().mode().iat[0] if s.notna().any() else None)
    o["category"] = cat.fillna(df["Category ID"].map(by_id)).fillna("Uncategorised")
    o["brand"] = df["Brand"].str.strip()
    o["sku"] = df["Asin"]
    o["title"] = fix_text(df["Title"]).str.strip()
    o["quantity"] = df["Quantity"]
    o["price"] = num(df["Price"])
    o["mrp"] = num(df["Price Higher"])
    o["discount"] = num(df["Discount ($)"])
    o["rank"] = num(df["Rank"])
    o["page"] = num(df["Page Number"])
    o["sponsored"] = truthy(df["Sponsored"])
    o["in_stock"] = truthy(df["Availability"])
    o["stock"] = num(df["Stock"])
    o["rating"] = num(df["Rating"])
    o["store_id"] = df["Store ID"]
    o["city"] = nearest_city(num(df["Latitude"]), num(df["Longitude"]))
    o["crawl_date"] = to_dt(df["Crawl Date"])
    return o


def _clean_bestsellers(df):
    o = pd.DataFrame(index=df.index)
    o["country_code"] = df["Country Code"].str.strip()
    o["country"] = o["country_code"].map(COUNTRIES).fillna(o["country_code"])
    o["category"] = fix_text(df["Category"]).str.strip()
    o["asin"] = df["Asin"]
    o["title"] = fix_text(df["Title"]).str.strip()
    o["rank"] = num(df["Rank"])
    o["price"] = num(df["Price"])
    cur = fix_text(df["Currency"]).str.strip()
    o["currency"] = cur.fillna(cur.groupby(o["country_code"]).transform(lambda s: s.dropna().mode().iat[0] if s.notna().any() else ""))
    o["rating"] = num(df["Rating"])
    o["rating_count"] = num(df["Rating Count"])
    o["crawl_date"] = to_dt(df["Crawl Date"])
    return o


def _clean_serp(df):
    o = pd.DataFrame(index=df.index)
    o["asin"] = df["Asin"]
    title = fix_text(df["Title"]).str.strip()
    # the crawler sometimes prefixes the brand twice ("GHAR SOAPS GHAR SOAPS …")
    o["title"] = title.str.replace(r"^(\b[\w ]{3,30}?\b) \1 ", r"\1 ", regex=True)
    o["keyword"] = df["Keyword"].str.strip()
    o["rank"] = num(df["Rank"])
    o["page"] = num(df["Page Number"])
    o["sponsored"] = truthy(df["Sponsored"])
    o["banner"] = df["Banner Type"].notna()
    o["price"] = num(df["Price"])
    o["mrp"] = num(df["Mrp"])
    o["rating"] = num(df["Rating"])
    o["rating_count"] = num(df["Rating Count"])
    o["results"] = num(df["No Products"])
    o["crawl_time"] = to_dt(df["Crawl Time"])
    o["crawl_date"] = o["crawl_time"].dt.normalize()
    o["currency"] = "₹"
    return o


def _clean_product_details(df):
    o = pd.DataFrame(index=df.index)
    o["sku"] = df["Asin"]
    o["title"] = fix_text(df["Title"]).str.strip()
    o["brand"] = df["Brand"].str.strip()
    o["quantity"] = df["Quantity"]
    o["mrp"] = num(df["Mrp"]).replace(0, np.nan)
    o["price"] = num(df["Price"]).replace(0, np.nan)
    o["discount"] = num(df["Discount Perc"])
    o["in_stock"] = truthy(df["Stock Status"])
    o["rating"] = num(df["Rating"])
    o["merchant"] = df["Merchant Name"].str.strip()
    o["store_id"] = df["Store ID"]
    o["city"] = nearest_city(num(df["Latitude"]), num(df["Longitude"]))
    o["crawl_time"] = to_dt(df["Crawl Time"])
    o["crawl_date"] = to_dt(df["Crawl Date"])
    return o


CLEANERS = {
    "brand_page": _clean_brand_page,
    "category": _clean_category,
    "bestsellers": _clean_bestsellers,
    "serp": _clean_serp,
    "product_details": _clean_product_details,
}


# ----------------------------------------------------------------- public API
def _scan():
    files = sorted(p for p in config.DATA_DIR.glob("*.csv"))
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files)


def load_all(force: bool = False) -> dict[str, pd.DataFrame]:
    """Return {dataset_id: cleaned DataFrame}. Re-reads only when files change."""
    with _lock:
        key = _scan()
        if not force and key == _cache["key"]:
            return _cache["frames"]
        parts: dict[str, list] = {}
        files: dict[str, list] = {}
        for path, _, _ in key:
            header = pd.read_csv(path, nrows=0, dtype=str).columns
            ds = detect(header)
            if not ds:
                continue
            raw = read_raw(path)
            if raw.empty:
                continue
            parts.setdefault(ds, []).append(CLEANERS[ds](raw).reset_index(drop=True))
            files.setdefault(ds, []).append(path)
        frames = {ds: pd.concat(p, ignore_index=True) for ds, p in parts.items()}
        _cache.update(key=key, frames=frames, files=files)
        return frames


def get(dataset: str) -> pd.DataFrame | None:
    return load_all().get(dataset)


def date_span(df: pd.DataFrame) -> str:
    col = "crawl_date"
    if col not in df or df[col].isna().all():
        return "n/a"
    lo, hi = df[col].min(), df[col].max()
    if lo == hi:
        return f"{lo:%d %b %Y}"
    return f"{lo:%d %b} – {hi:%d %b %Y}"


def date_bounds(df: pd.DataFrame):
    """(min, max) crawl date as ISO strings, or (None, None)."""
    if "crawl_date" not in df or df["crawl_date"].isna().all():
        return None, None
    return f"{df['crawl_date'].min():%Y-%m-%d}", f"{df['crawl_date'].max():%Y-%m-%d}"


def filter_dates(df: pd.DataFrame, rng) -> tuple[pd.DataFrame, str]:
    """Apply a {'preset': all|7|30|90|custom, 'from', 'to'} range. Returns (frame, description)."""
    if not rng or rng.get("preset", "all") == "all" or "crawl_date" not in df:
        return df, ""
    today = pd.Timestamp.now().normalize()
    if rng["preset"] == "custom":
        lo = pd.to_datetime(rng.get("from"), errors="coerce")
        hi = pd.to_datetime(rng.get("to"), errors="coerce")
        lo = df["crawl_date"].min() if pd.isna(lo) else lo
        hi = df["crawl_date"].max() if pd.isna(hi) else hi
        label = f"{lo:%d %b %Y} – {hi:%d %b %Y}"
    else:
        days = int(rng["preset"])
        lo, hi, label = today - pd.Timedelta(days=days - 1), today, f"last {days} days"
    out = df[(df["crawl_date"] >= lo) & (df["crawl_date"] <= hi)]
    if out.empty:
        raise ValueError(f"There is no data for {label}. This dataset covers {date_span(df)} – widen the date range.")
    return out, f"dates: {label}"


def is_nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))

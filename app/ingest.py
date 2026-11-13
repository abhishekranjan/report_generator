"""Import raw crawl exports into the data folder.

    python -m app.ingest "C:\\path\\Brand Page.csv" "C:\\path\\SERP.csv" ...

Each file is recognised by its columns, stripped of blank padding rows and
entirely-empty columns, and saved as data/<dataset>__<name>.csv.
"""
import re
import sys
from pathlib import Path

from . import config, data


def ingest(paths) -> list[str]:
    done = []
    for raw in paths:
        p = Path(raw)
        df = data.read_raw(p)
        ds = data.detect(df.columns)
        if not ds:
            print(f"SKIP  {p.name}: columns do not match a known crawl type")
            continue
        keep = [c for c in df.columns if df[c].notna().any() or c in data.SIGNATURES[ds]]
        slug = re.sub(r"[^a-z0-9]+", "_", p.stem.lower()).strip("_")
        out = config.DATA_DIR / f"{ds}__{slug}.csv"
        df[keep].to_csv(out, index=False, encoding="utf-8")
        print(f"OK    {p.name} -> {out.name}  [{data.DATASET_LABELS[ds]}]  {len(df):,} rows, {len(keep)} columns")
        done.append(str(out))
    return done


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ingest(sys.argv[1:])

"""Brand shelf health – from the Blinkit brand-page crawl."""
import pandas as pd

from .base import (as_list, chart, cnt, dec, field, join_names, kpi, money, opts, pct, section, table, top_n, trunc)

ID = "brand_shelf"
NAME = "Brand Shelf Health"
DATASET = "brand_page"
DESCRIPTION = ("How one brand's full range shows up on Blinkit: assortment by sub-brand, in-stock rate by pincode, "
               "out-of-stock hotspots, discount depth and shelf position.")
KEYWORDS = ["brand", "portfolio", "assortment", "sub-brand", "pincode", "out of stock", "oos", "availability",
            "stock", "discount", "blinkit", "shelf", "range"]
ENTITY_FIELD = "brand"


def fields(df):
    fam = df["brand_family"].value_counts().index.tolist()
    sub = df.groupby(["brand_family", "brand"]).size().reset_index()
    pins = df.groupby(["brand_family", "pincode", "pin_city"]).size().reset_index()
    pin_labels = [f"{p} · {c}" if c else p for p, c in zip(pins["pincode"], pins["pin_city"])]
    return [
        field("brand", "Brand", "select", True, opts(fam), "The brand whose Blinkit brand page is analysed."),
        field("sub_brands", "Sub-brands", "multi", False,
              opts(sub["brand"], parents=sub["brand_family"]), "Leave empty to cover the whole range.", "brand"),
        field("pincodes", "Pincodes", "multi", False,
              opts(pins["pincode"], pin_labels, pins["brand_family"]), "Leave empty for every pincode crawled.", "brand") | {"literal_only": True},
    ]


def build(df, p):
    n = top_n(p)
    d = df[df["brand_family"] == p["brand"]]
    scope = []
    if as_list(p.get("sub_brands")):
        d = d[d["brand"].isin(as_list(p["sub_brands"]))]
        scope.append("sub-brands: " + ", ".join(as_list(p["sub_brands"])))
    if as_list(p.get("pincodes")):
        d = d[d["pincode"].isin(as_list(p["pincodes"]))]
        scope.append("pincodes: " + ", ".join(as_list(p["pincodes"])))
    if d.empty:
        raise ValueError("No rows match that brand / filter combination.")

    avail = d["in_stock"].mean() * 100
    sku = d.groupby("sku").agg(title=("title", "first"), qty=("quantity", "first"), brand=("brand", "first"),
                               stores=("store_id", "nunique"), listings=("sku", "size"),
                               avail=("in_stock", "mean"), mrp=("mrp", "median"), price=("price", "median"),
                               disc=("discount", "mean"), rating=("rating", "mean"), pos=("position", "mean"),
                               prices=("price", "nunique"))
    sku["avail"] *= 100
    kpis = [
        kpi("SKUs listed", cnt(len(sku))),
        kpi("Stores covered", cnt(d["store_id"].nunique()), f"{d['pincode'].nunique()} pincodes"),
        kpi("In-stock rate", pct(avail), f"{cnt((~d['in_stock']).sum())} of {cnt(len(d))} listings out of stock"),
        kpi("Average discount", pct(sku["disc"].mean()), f"{pct((sku['disc'] > 0).mean() * 100)} of SKUs discounted"),
        kpi("Average rating", dec(sku["rating"].mean(), 2), "SKU-level mean"),
        kpi("Median price", money(sku["price"].median())),
    ]
    sections = []

    # 1 portfolio mix
    g = d.groupby("brand").agg(listings=("sku", "size"), skus=("sku", "nunique"), avail=("in_stock", "mean"),
                               disc=("discount", "mean"), rating=("rating", "mean")).sort_values("listings", ascending=False)
    g["share"] = g["listings"] / g["listings"].sum() * 100
    g["avail"] *= 100
    facts = [f"{p['brand']} lists {len(sku)} SKUs across {len(g)} sub-brand(s) in {d['store_id'].nunique()} stores."]
    if len(g) > 1:
        facts.append(f"{g.index[0]} is the largest line with {pct(g['share'].iat[0])} of listings and {g['skus'].iat[0]} SKUs.")
        weak = g[g["listings"] >= 20].sort_values("avail")
        if len(weak):
            facts.append(f"Lowest in-stock rate among sub-brands: {weak.index[0]} at {pct(weak['avail'].iat[0])}; "
                         f"highest: {weak.index[-1]} at {pct(weak['avail'].iat[-1])}.")
    ch = chart("barh", "Share of listings by sub-brand", g.index[:n], g["share"][:n], "pct") if len(g) > 1 else None
    tb = table(["Sub-brand", "SKUs", "Listings", "In stock", "Avg discount", "Rating"],
               [[b, cnt(r.skus), cnt(r.listings), pct(r.avail), pct(r.disc), dec(r.rating, 2)] for b, r in g.head(n).iterrows()],
               [3, 1, 1.2, 1.2, 1.4, 1])
    sections.append(section("portfolio", "Portfolio mix", facts, ch, tb))

    # 2 availability by pincode
    g = d.groupby("pincode").agg(listings=("sku", "size"), avail=("in_stock", "mean"), stores=("store_id", "nunique"),
                                 city=("pin_city", "first"))
    g["avail"] *= 100
    g = g[g["listings"] >= min(10, g["listings"].max())].sort_values("avail")
    if len(g) > 1:
        low = g[g["avail"] < 70]
        name = lambda i: f"{g.index[i]}, {g['city'].iat[i]}" if g["city"].iat[i] else g.index[i]
        facts = [f"In-stock rate ranges from {pct(g['avail'].iat[0])} (pincode {name(0)}) to "
                 f"{pct(g['avail'].iat[-1])} (pincode {name(-1)}) across {len(g)} pincodes.",
                 f"{len(low)} pincode(s) sit below a 70% in-stock rate." if len(low) else
                 "Every pincode holds an in-stock rate of 70% or better."]
        w = g.head(n)
        ch = chart("barh", f"Lowest in-stock pincodes (overall {pct(avail)})",
                   [f"{i} {r.city}".strip() for i, r in w.iterrows()], w["avail"], "pct", xmax=100)
        tb = table(["Pincode", "City", "Stores", "Listings", "In stock"],
                   [[i, r.city, cnt(r.stores), cnt(r.listings), pct(r.avail)] for i, r in w.iterrows()], [1.2, 1.6, 1, 1, 1],
                   ["l", "l", "r", "r", "r"])
        sections.append(section("pincode_availability", "Availability by pincode", facts, ch, tb))

    # 3 out-of-stock hotspots
    wide = sku[sku["stores"] >= min(5, sku["stores"].max())].copy()
    wide["oos"] = 100 - wide["avail"]
    hot = wide[wide["oos"] > 0].sort_values(["oos", "stores"], ascending=False).head(n)
    if len(hot):
        facts = [f"{(wide['oos'] >= 50).sum()} SKU(s) are out of stock in at least half the stores that list them.",
                 f"Worst affected: {trunc(hot['title'].iat[0], 60)} ({hot['qty'].iat[0]}), out of stock in "
                 f"{pct(hot['oos'].iat[0])} of {hot['stores'].iat[0]} stores."]
        tb = table(["SKU", "Pack", "Stores", "Out of stock"],
                   [[trunc(r.title, 52), r.qty, cnt(r.stores), pct(r.oos)] for r in hot.itertuples()], [5, 1.3, 1, 1.3])
        sections.append(section("oos_hotspots", "Out-of-stock hotspots", facts, None, tb))

    # 4 pricing and discounting
    bands = pd.cut(sku["disc"].fillna(0), [-0.01, 0.01, 10, 20, 30, 100],
                   labels=["No discount", "1–10%", "10–20%", "20–30%", "30%+"]).value_counts(sort=False)
    varied = (sku["prices"] > 1).sum()
    deep = sku.sort_values("disc", ascending=False).head(n)
    facts = [f"{pct((sku['disc'].fillna(0) <= 0.01).mean() * 100)} of SKUs sell at full MRP; the average discount is {pct(sku['disc'].mean())}.",
             f"{varied} SKU(s) ({pct(varied / len(sku) * 100)}) show more than one selling price across stores – a price-consistency flag.",
             f"Deepest discount: {trunc(deep['title'].iat[0], 60)} at {pct(deep['disc'].iat[0])} off."]
    ch = chart("bar", "SKUs by discount depth", bands.index, bands.values, "num")
    tb = table(["SKU", "Pack", "MRP", "Price", "Discount"],
               [[trunc(r.title, 50), r.qty, money(r.mrp), money(r.price), pct(r.disc)] for r in deep.itertuples()],
               [5, 1.3, 1, 1, 1.2])
    sections.append(section("pricing", "Pricing and discounting", facts, ch, tb))

    # 5 shelf position
    lead = sku[sku["stores"] >= min(5, sku["stores"].max())].sort_values("pos").head(n)
    risk = lead[lead["avail"] < 80]
    facts = [f"The best-placed SKU on the brand page is {trunc(lead['title'].iat[0], 60)} (average position {dec(lead['pos'].iat[0])}).",
             (f"{len(risk)} of the top {len(lead)} placed SKUs are in stock less than 80% of the time, led by "
              f"{join_names([trunc(t, 40) for t in risk['title']], 2)}." if len(risk) else
              f"All top {len(lead)} placed SKUs hold an in-stock rate of 80% or better.")]
    tb = table(["SKU", "Pack", "Avg position", "In stock", "Rating"],
               [[trunc(r.title, 50), r.qty, dec(r.pos), pct(r.avail), dec(r.rating, 1)] for r in lead.itertuples()],
               [5, 1.3, 1.3, 1.1, 1])
    sections.append(section("shelf_position", "Shelf position on the brand page", facts, None, tb))

    return {
        "subject": p["brand"], "scope": "; ".join(scope) or "Full range, all pincodes crawled", "rows": len(d),
        "kpis": kpis, "sections": sections,
        "definitions": [
            "In-stock rate: share of SKU × store listings marked in stock at crawl time.",
            "Discount: (MRP − selling price) ÷ MRP, averaged per SKU across stores.",
            "Position: listing order on the brand page (page × rank); lower is better.",
        ],
    }

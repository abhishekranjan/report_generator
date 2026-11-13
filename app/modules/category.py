"""Category landscape – from the Blinkit category-listing crawl."""
import numpy as np
import pandas as pd

from .base import (as_list, chart, cnt, dec, field, join_names, kpi, money, opts, pct, section, table, top_n, trunc)

ID = "category_landscape"
NAME = "Category Landscape"
DATASET = "category"
DESCRIPTION = ("Competitive view of one Blinkit category: brand share of shelf, sponsored placements, price "
               "architecture, availability by city and the most visible products. Optionally benchmarks one brand.")
CHANNEL = "Blinkit"
SECTIONS = [
    ("share_of_shelf", "Share of shelf", "Brand share of listings and of first-page listings"),
    ("sponsored", "Sponsored placements", "Which brands buy ad slots and how much they rely on them"),
    ("pricing", "Price architecture", "Price bands, median price, most discounted products"),
    ("city_availability", "Availability by city", "In-stock rate per city, weakest first"),
    ("top_products", "Most visible products", "Products most often on the first page"),
    ("focus_brand", "Focus brand versus the category", "Scorecard of one brand against category averages (needs a focus brand)"),
]
KEYWORDS = ["category", "competition", "competitor", "share of shelf", "market", "landscape", "sponsored", "ads",
            "price band", "benchmark", "city", "blinkit", "players"]
ENTITY_FIELD = "category"


def fields(df):
    cats = df["category"].value_counts().index.tolist()
    b = df.groupby(["category", "brand"]).size().reset_index(name="n").sort_values("n", ascending=False)
    c = df.groupby(["category", "city"]).size().reset_index(name="n").sort_values("n", ascending=False)
    return [
        field("category", "Category", "select", True, opts(cats), "The Blinkit category to analyse."),
        field("focus_brand", "Focus brand", "select", False, opts(b["brand"], parents=b["category"]),
              "Optional – benchmark this brand against the category.", "category"),
        field("competitors", "Competitors", "multi", False, opts(b["brand"], parents=b["category"]),
              "Brands to compare in the share-of-shelf view. Leave empty for the top brands.", "category"),
        field("cities", "Cities", "multi", False, opts(c["city"], parents=c["category"]),
              "Leave empty for every city crawled.", "category"),
    ]


def _nice_bins(prices):
    qs = np.unique(np.quantile(prices.dropna(), [0, 0.2, 0.4, 0.6, 0.8, 1.0]))
    def rnd(v):
        step = 5 if v < 100 else 10 if v < 500 else 50 if v < 2000 else 100
        return float(round(v / step) * step)
    edges = sorted(set([0.0] + [rnd(q) for q in qs[1:-1]]))
    return edges + [float("inf")]


def build(df, p):
    n = top_n(p)
    d = df[df["category"] == p["category"]]
    scope = []
    if as_list(p.get("cities")):
        d = d[d["city"].isin(as_list(p["cities"]))]
        scope.append("cities: " + ", ".join(as_list(p["cities"])))
    if d.empty:
        raise ValueError("No rows match that category / filter combination.")
    focus = p.get("focus_brand") or None
    if focus and focus not in set(d["brand"]):
        focus = None
    total = len(d)
    avail = d["in_stock"].mean() * 100
    spons = d["sponsored"].mean() * 100
    prod = d.groupby("sku").agg(title=("title", "first"), brand=("brand", "first"), qty=("quantity", "first"),
                                listings=("sku", "size"), price=("price", "median"), mrp=("mrp", "median"),
                                disc=("discount", "mean"), rating=("rating", "mean"), avail=("in_stock", "mean"),
                                p1=("page", lambda s: (s == 1).sum()), stores=("store_id", "nunique"))
    prod["avail"] *= 100

    kpis = [
        kpi("Brands", cnt(d["brand"].nunique())),
        kpi("Products", cnt(len(prod)), f"{cnt(total)} listings in {cnt(d['store_id'].nunique())} stores"),
        kpi("In-stock rate", pct(avail)),
        kpi("Sponsored share", pct(spons, 1), "of all listings"),
        kpi("Average discount", pct(d["discount"].mean())),
        kpi("Median price", money(prod["price"].median())),
    ]
    sections = []

    # 1 share of shelf
    g = d.groupby("brand").agg(listings=("sku", "size"), products=("sku", "nunique"), price=("price", "median"),
                               disc=("discount", "mean"), avail=("in_stock", "mean"), rating=("rating", "mean"),
                               p1=("page", lambda s: (s == 1).sum()), spons=("sponsored", "sum"))
    g["share"] = g["listings"] / total * 100
    g["p1_share"] = g["p1"] / max(1, (d["page"] == 1).sum()) * 100
    g["avail"] *= 100
    g = g.sort_values("share", ascending=False)
    top = g.head(n)
    facts = [f"{len(g)} brands compete in {p['category']}; the top 3 ({join_names(g.index[:3])}) hold "
             f"{pct(g['share'][:3].sum())} of all listings.",
             f"{g.index[0]} leads with {pct(g['share'].iat[0], 1)} share of shelf and {g['products'].iat[0]} products."]
    if focus:
        rank = list(g.index).index(focus) + 1
        facts.append(f"{focus} ranks #{rank} of {len(g)} brands with {pct(g.loc[focus, 'share'], 1)} share of shelf "
                     f"and {pct(g.loc[focus, 'p1_share'], 1)} of first-page listings.")
        if focus not in top.index:
            top = pd.concat([top.iloc[:-1], g.loc[[focus]]])
    comp = [c for c in as_list(p.get("competitors")) if c in g.index]
    if comp:
        chosen = list(dict.fromkeys(([focus] if focus else []) + comp))
        top = g.loc[chosen].sort_values("share", ascending=False)
        scope.append("compared brands: " + ", ".join(chosen))
        facts.append(f"The selected brands ({join_names(chosen, 6)}) together hold {pct(top['share'].sum(), 1)} of all listings.")
    ch = chart("barh", "Share of shelf by brand (% of listings)", top.index, top["share"], "pct1", highlight=focus)
    tb = table(["Brand", "Share", "Page-1 share", "Products", "Median price", "Discount", "In stock", "Rating"],
               [[trunc(b, 26), pct(r.share, 1), pct(r.p1_share, 1), cnt(r.products), money(r.price), pct(r.disc),
                 pct(r.avail), dec(r.rating, 1)] for b, r in top.iterrows()], [3, 1, 1.3, 1.1, 1.3, 1.1, 1.1, 0.9])
    sections.append(section("share_of_shelf", "Share of shelf", facts, ch, tb))

    # 2 sponsored
    sp = g[g["spons"] > 0].sort_values("spons", ascending=False)
    if len(sp):
        sp = sp.assign(sshare=sp["spons"] / sp["spons"].sum() * 100, rely=sp["spons"] / sp["listings"] * 100)
        facts = [f"{pct(spons, 1)} of listings are sponsored; {len(sp)} of {len(g)} brands buy placements.",
                 f"{sp.index[0]} takes {pct(sp['sshare'].iat[0])} of sponsored slots; sponsored placements make up "
                 f"{pct(sp['rely'].iat[0])} of its own listings."]
        if focus:
            facts.append(f"{focus} holds {pct(sp.loc[focus, 'sshare'], 1)} of sponsored slots." if focus in sp.index
                         else f"{focus} has no sponsored placements in this crawl.")
        s = sp.head(n)
        ch = chart("barh", "Share of sponsored placements by brand", s.index, s["sshare"], "pct", highlight=focus)
        tb = table(["Brand", "Sponsored listings", "Share of sponsored", "Sponsored % of own listings"],
                   [[trunc(b, 30), cnt(r.spons), pct(r.sshare), pct(r.rely)] for b, r in s.iterrows()], [3, 1.5, 1.5, 2])
        sections.append(section("sponsored", "Sponsored placements", facts, ch, tb))

    # 3 price architecture
    edges = _nice_bins(prod["price"])
    labels = [f"Under ₹{edges[1]:,.0f}"] + [f"₹{a:,.0f}–{b:,.0f}" for a, b in zip(edges[1:-2], edges[2:-1])] + [f"₹{edges[-2]:,.0f}+"]
    bands = pd.cut(prod["price"], edges, labels=labels, right=False).value_counts(sort=False)
    deep = prod.sort_values("disc", ascending=False).head(n)
    facts = [f"Median product price is {money(prod['price'].median())}; the middle 50% of products sit between "
             f"{money(prod['price'].quantile(.25))} and {money(prod['price'].quantile(.75))}.",
             f"The busiest price band is {bands.idxmax()} with {bands.max()} products.",
             f"{pct((prod['disc'] > 0).mean() * 100)} of products carry a discount; the average depth is {pct(d['discount'].mean())}."]
    if focus:
        facts.append(f"{focus}'s median price is {money(g.loc[focus, 'price'])} against a category median of {money(prod['price'].median())}.")
    ch = chart("bar", "Products by price band", bands.index, bands.values, "num")
    tb = table(["Most discounted products", "Brand", "MRP", "Price", "Discount"],
               [[trunc(r.title, 46), trunc(r.brand, 18), money(r.mrp), money(r.price), pct(r.disc)] for r in deep.itertuples()],
               [4.5, 1.8, 1, 1, 1.1])
    sections.append(section("pricing", "Price architecture", facts, ch, tb))

    # 4 availability by city
    c = d.groupby("city").agg(listings=("sku", "size"), stores=("store_id", "nunique"), avail=("in_stock", "mean"))
    c["avail"] *= 100
    c = c[c["listings"] >= min(30, c["listings"].max())].sort_values("avail")
    if len(c) > 1:
        facts = [f"In-stock rate runs from {pct(c['avail'].iat[0])} in {c.index[0]} to {pct(c['avail'].iat[-1])} in "
                 f"{c.index[-1]} (category average {pct(avail)})."]
        if focus:
            fc = d[d["brand"] == focus].groupby("city")["in_stock"].agg(["mean", "size"])
            fc = fc[fc["size"] >= 5].sort_values("mean")
            if len(fc) > 1 and round(fc["mean"].iat[0], 2) != round(fc["mean"].iat[-1], 2):
                facts.append(f"{focus} is weakest in {fc.index[0]} ({pct(fc['mean'].iat[0] * 100)} in stock) and "
                             f"strongest in {fc.index[-1]} ({pct(fc['mean'].iat[-1] * 100)}).")
        w = c.head(max(n, 12))
        ch = chart("barh", "In-stock rate by city (lowest first)", w.index, w["avail"], "pct", xmax=100)
        tb = table(["City", "Stores", "Listings", "In stock"],
                   [[i, cnt(r.stores), cnt(r.listings), pct(r.avail)] for i, r in w.iterrows()], [2, 1, 1, 1])
        sections.append(section("city_availability", "Availability by city", facts, ch, tb))

    # 5 most visible products
    vis = prod.sort_values(["p1", "listings"], ascending=False).head(n)
    facts = [f"The most visible product is {trunc(vis['title'].iat[0], 60)} by {vis['brand'].iat[0]}, on the first "
             f"page in {cnt(vis['p1'].iat[0])} store listings.",
             f"{vis['brand'].value_counts().index[0]} owns {vis['brand'].value_counts().iat[0]} of the top {len(vis)} most visible products."]
    tb = table(["Product", "Brand", "Page-1 listings", "Price", "In stock", "Rating"],
               [[trunc(r.title, 44), trunc(r.brand, 18), cnt(r.p1), money(r.price), pct(r.avail), dec(r.rating, 1)]
                for r in vis.itertuples()], [4.5, 1.8, 1.4, 1, 1, 0.9])
    sections.append(section("top_products", "Most visible products", facts, None, tb))

    # 6 focus-brand scorecard
    if focus:
        f = g.loc[focus]
        rows = [["Share of shelf", pct(f.share, 1), pct(100 / len(g), 1) + " (avg brand)"],
                ["Products listed", cnt(f.products), dec(g["products"].mean(), 1) + " (avg brand)"],
                ["Median price", money(f.price), money(prod["price"].median())],
                ["Average discount", pct(f.disc), pct(d["discount"].mean())],
                ["In-stock rate", pct(f.avail), pct(avail)],
                ["Average rating", dec(f.rating, 2), dec(d["rating"].mean(), 2)],
                ["Sponsored % of own listings", pct(f.spons / f.listings * 100, 1), pct(spons, 1)]]
        gap = f.avail - avail
        facts = [f"{focus} is in stock {pct(f.avail)} of the time, {abs(gap):.0f} points {'above' if gap >= 0 else 'below'} the category.",
                 f"It discounts {pct(f.disc)} on average versus {pct(d['discount'].mean())} for the category."]
        sections.append(section("focus_brand", f"{focus} versus the category", facts, None,
                                table(["Metric", focus, "Category"], rows, [2.5, 1.5, 2])))

    return {
        "subject": p["category"] + (f" – {focus}" if focus else ""),
        "scope": "; ".join(scope) or "All cities crawled", "rows": total, "kpis": kpis, "sections": sections,
        "definitions": [
            "Share of shelf: a brand's share of all product listings across stores and result pages.",
            "Page-1 share: a brand's share of listings on the first results page.",
            "City: derived from store coordinates (nearest major city).",
        ],
    }

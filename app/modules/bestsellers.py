"""Marketplace bestsellers – from the Amazon bestseller-list crawl."""
import pandas as pd

from .base import (as_list, chart, cnt, dec, field, join_names, kpi, money, opts, pct, section, table, top_n, trunc)

ID = "bestsellers"
NAME = "Amazon Bestseller Pulse"
DATASET = "bestsellers"
DESCRIPTION = ("What is winning on Amazon bestseller lists in one country: category overview, price points, rating "
               "and review depth, chart-toppers and low-review challengers breaking into the top 20.")
KEYWORDS = ["bestseller", "best seller", "best-selling", "top selling", "amazon", "top 100", "trending", "country",
            "international", "reviews", "ratings", "winning products"]
ENTITY_FIELD = "country"


def fields(df):
    c = df["country"].value_counts().index.tolist()
    cats = df.groupby(["country", "category"]).size().reset_index()
    return [
        field("country", "Country", "select", True, opts(c), "Amazon marketplace to analyse."),
        field("categories", "Categories", "multi", False, opts(cats["category"], parents=cats["country"]),
              "Leave empty to cover every bestseller list crawled.", "country"),
    ]


def build(df, p):
    n = top_n(p)
    d = df[df["country"] == p["country"]]
    scope = []
    if as_list(p.get("categories")):
        d = d[d["category"].isin(as_list(p["categories"]))]
        scope.append("categories: " + ", ".join(as_list(p["categories"])))
    if d.empty:
        raise ValueError("No rows match that country / filter combination.")
    cur = d["currency"].dropna().mode().iat[0] if d["currency"].notna().any() else ""
    m = lambda v: money(v, cur)

    kpis = [
        kpi("Bestseller lists", cnt(d["category"].nunique())),
        kpi("Ranked products", cnt(len(d)), f"{cnt(d['asin'].nunique())} unique ASINs"),
        kpi("Median price", m(d["price"].median()), f"{pct(d['price'].notna().mean() * 100)} of listings priced"),
        kpi("Average rating", dec(d["rating"].mean(), 2)),
        kpi("Median review count", cnt(d["rating_count"].median())),
        kpi("Rated 4.5 or higher", pct((d["rating"] >= 4.5).sum() / max(1, d["rating"].notna().sum()) * 100)),
    ]
    sections = []

    # 1 category overview
    g = d.groupby("category").agg(products=("asin", "size"), price=("price", "median"), rating=("rating", "mean"),
                                  reviews=("rating_count", "median")).sort_values("reviews", ascending=False)
    if len(g) > 1:
        facts = [f"{len(g)} bestseller lists are tracked in {p['country']}.",
                 f"Review depth is highest in {g.index[0]} (median {cnt(g['reviews'].iat[0])} reviews per bestseller) and "
                 f"lowest in {g.index[-1]} ({cnt(g['reviews'].iat[-1])}).",
                 f"Priciest list by median: {g['price'].idxmax()} at {m(g['price'].max())}; cheapest: "
                 f"{g['price'].idxmin()} at {m(g['price'].min())}."]
        t = g.head(n)
        ch = chart("barh", "Median review count per bestseller, by category", [trunc(i, 34) for i in t.index], t["reviews"], "num")
        tb = table(["Category", "Products", "Median price", "Avg rating", "Median reviews"],
                   [[trunc(i, 40), cnt(r.products), m(r.price), dec(r.rating, 2), cnt(r.reviews)] for i, r in t.iterrows()],
                   [3.5, 1, 1.3, 1.1, 1.4])
        sections.append(section("categories", "Category overview", facts, ch, tb))

    # 2 rating profile
    r = d["rating"].dropna()
    if len(r):
        bands = pd.cut(r, [0, 3.95, 4.25, 4.45, 4.65, 5.01], labels=["Below 4.0", "4.0–4.2", "4.3–4.4", "4.5–4.6", "4.7+"],
                       right=False).value_counts(sort=False)
        share = bands / bands.sum() * 100
        facts = [f"{pct(share.iloc[3:].sum())} of rated bestsellers score 4.5 or higher; only {pct(share.iloc[0])} sit below 4.0.",
                 f"{pct(d['rating'].isna().mean() * 100)} of ranked products have no rating yet."]
        ch = chart("bar", "Bestsellers by star rating (% of rated products)", bands.index, share.values, "pct")
        sections.append(section("ratings", "Rating profile", facts, ch, None))

    # 3 review depth by rank
    b = pd.cut(d["rank"], [0, 10, 25, 50, 100], labels=["Rank 1–10", "Rank 11–25", "Rank 26–50", "Rank 51–100"])
    rb = d.groupby(b, observed=True).agg(reviews=("rating_count", "median"), rating=("rating", "mean"),
                                         price=("price", "median"), n=("asin", "size"))
    if len(rb) > 1 and rb["reviews"].notna().any():
        hi, lo = rb["reviews"].iat[0], rb["reviews"].iat[-1]
        facts = [f"Top-10 products carry a median of {cnt(hi)} reviews versus {cnt(lo)} for ranks 51–100"
                 + (f" – {hi / lo:.1f}× the review depth." if lo and lo > 0 else "."),
                 f"Median price in the top 10 is {m(rb['price'].iat[0])} against {m(rb['price'].iat[-1])} in ranks 51–100."]
        ch = chart("bar", "Median review count by rank bucket", rb.index, rb["reviews"], "num")
        tb = table(["Rank bucket", "Products", "Median reviews", "Avg rating", "Median price"],
                   [[i, cnt(x.n), cnt(x.reviews), dec(x.rating, 2), m(x.price)] for i, x in rb.iterrows()], [2, 1, 1.4, 1.1, 1.3])
        sections.append(section("review_depth", "Review depth by rank", facts, ch, tb))

    # 4 chart toppers
    tops = d[d["rank"] == 1].sort_values("rating_count", ascending=False).head(n)
    if len(tops):
        facts = [f"The most-reviewed #1 is {trunc(tops['title'].iat[0], 70)} in {tops['category'].iat[0]} "
                 f"with {cnt(tops['rating_count'].iat[0])} reviews at {dec(tops['rating'].iat[0])}★."]
        tb = table(["#1 product", "Category", "Price", "Rating", "Reviews"],
                   [[trunc(x.title, 48), trunc(x.category, 22), m(x.price), dec(x.rating), cnt(x.rating_count)]
                    for x in tops.itertuples()], [4.5, 2.2, 1.1, 0.8, 1.1])
        sections.append(section("chart_toppers", "Chart-toppers", facts, None, tb))

    # 5 challengers
    ch_ = d[(d["rank"] <= 20) & (d["rating_count"].fillna(0) < 50)].sort_values(["rank", "rating_count"]).head(n)
    if len(ch_):
        total20 = (d["rank"] <= 20).sum()
        allc = d[(d["rank"] <= 20) & (d["rating_count"].fillna(0) < 50)]
        facts = [f"{cnt(len(allc))} of {cnt(total20)} top-20 placements ({pct(len(allc) / total20 * 100)}) belong to products with "
                 f"fewer than 50 reviews – new entrants winning on velocity rather than review history.",
                 f"They cluster in {join_names(allc['category'].value_counts().index[:3])}."]
        tb = table(["Challenger product", "Category", "Rank", "Price", "Reviews"],
                   [[trunc(x.title, 48), trunc(x.category, 22), cnt(x.rank), m(x.price), cnt(x.rating_count) if x.rating_count == x.rating_count else "none"]
                    for x in ch_.itertuples()], [4.5, 2.2, 0.8, 1.1, 1])
        sections.append(section("challengers", "Low-review challengers in the top 20", facts, None, tb))

    return {
        "subject": f"Amazon {p['country']}", "scope": "; ".join(scope) or "All bestseller lists crawled",
        "rows": len(d), "kpis": kpis, "sections": sections,
        "definitions": [
            "Rank: position on the Amazon bestseller list for the category (1–100).",
            "Review count: number of customer ratings shown on the listing at crawl time.",
            f"Prices are in local currency ({cur or 'as listed'}); unpriced listings are excluded from price metrics.",
        ],
    }

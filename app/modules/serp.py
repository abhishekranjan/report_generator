"""Search visibility – from the Amazon SERP crawl."""
from .base import (as_list, chart, cnt, dec, field, kpi, money, opts, pct, section, table, top_n, trunc)

ID = "keyword_visibility"
NAME = "Search Visibility Tracker"
DATASET = "serp"
DESCRIPTION = ("How one product ranks in Amazon search across tracked keywords: organic vs sponsored rank, page-1 "
               "presence, rank trend over time and price/offer changes.")
KEYWORDS = ["keyword", "search", "serp", "rank", "ranking", "visibility", "organic", "sponsored", "seo", "ads",
            "position", "search results", "trend"]
ENTITY_FIELD = "product"


def fields(df):
    pr = df.groupby("asin").agg(title=("title", "first"), n=("asin", "size")).sort_values("n", ascending=False)
    kw = df.groupby(["asin", "keyword"]).size().reset_index()
    return [
        field("product", "Product (ASIN)", "select", True,
              opts(pr.index, [f"{trunc(t, 60)} ({a})" for a, t in pr["title"].items()]), "The product being tracked."),
        field("keywords", "Keywords", "multi", False, opts(kw["keyword"], parents=kw["asin"]),
              "Leave empty to cover every tracked keyword.", "product") | {"quoted_only": True},
    ]


def build(df, p):
    n = top_n(p)
    d = df[df["asin"] == p["product"]]
    scope = []
    if as_list(p.get("keywords")):
        d = d[d["keyword"].isin(as_list(p["keywords"]))]
        scope.append("keywords: " + ", ".join(as_list(p["keywords"])))
    if d.empty:
        raise ValueError("No rows match that product / keyword combination.")
    title = d["title"].iloc[0]
    org, sp = d[~d["sponsored"]], d[d["sponsored"]]
    snaps = d.groupby(["keyword", "crawl_time"]).ngroups
    org_snaps = org.groupby(["keyword", "crawl_time"]).ngroups

    kpis = [
        kpi("Keywords tracked", cnt(d["keyword"].nunique()), f"{cnt(d['crawl_time'].nunique())} crawl snapshots"),
        kpi("Best organic rank", cnt(org["rank"].min()) if len(org) else "–"),
        kpi("Average organic rank", dec(org["rank"].mean()) if len(org) else "–"),
        kpi("Average sponsored rank", dec(sp["rank"].mean()) if len(sp) else "–"),
        kpi("Sponsored share", pct(len(sp) / len(d) * 100), "of all appearances"),
        kpi("Organic presence", pct(org_snaps / max(1, snaps) * 100), "of keyword snapshots with an organic result"),
    ]
    sections = []

    # 1 keyword scorecard
    g = d.groupby("keyword").agg(apps=("rank", "size"), p1=("page", lambda s: (s == 1).mean() * 100),
                                 spons=("sponsored", lambda s: s.mean() * 100))
    g["org"] = org.groupby("keyword")["rank"].mean()
    g["best"] = org.groupby("keyword")["rank"].min()
    g["sp"] = sp.groupby("keyword")["rank"].mean()
    g = g.sort_values("org", na_position="last")
    has = g.dropna(subset=["org"])
    facts = []
    if len(has):
        facts.append(f"Strongest organic keyword: “{has.index[0]}” (average rank {dec(has['org'].iat[0])}, best {cnt(has['best'].iat[0])}).")
        if len(has) > 1:
            facts.append(f"Weakest organic keyword: “{has.index[-1]}” (average rank {dec(has['org'].iat[-1])}).")
    none = g[g["org"].isna()]
    if len(none):
        facts.append("No organic ranking at all – visibility is fully paid – on: " + ", ".join(f"“{k}”" for k in none.index[:4]) + ".")
    gap = g.dropna(subset=["org", "sp"])
    if len(gap):
        facts.append(f"Sponsored placements average rank {dec(sp['rank'].mean())} versus {dec(org['rank'].mean())} organically – "
                     f"ads lift the product by about {abs(org['rank'].mean() - sp['rank'].mean()):.0f} positions.")
    ch = chart("barh", "Average organic rank by keyword (lower is better)", has.index, has["org"], "dec") if len(has) else None
    tb = table(["Keyword", "Times seen", "Organic rank (avg)", "Organic rank (best)", "Sponsored rank (avg)", "On page 1", "Paid share"],
               [[trunc(k, 34), cnt(r.apps), dec(r.org), cnt(r.best), dec(r.sp), pct(r.p1), pct(r.spons)] for k, r in g.head(n).iterrows()],
               [3, 1.1, 1.5, 1.5, 1.6, 1.1, 1.1])
    sections.append(section("keyword_scorecard", "Keyword scorecard", facts, ch, tb))

    # 2 rank trend
    if len(org) and org["crawl_time"].nunique() > 3:
        o = org.assign(bucket=org["crawl_time"].dt.floor("6h"))
        keys = o["keyword"].value_counts().index[:4].tolist()
        piv = o[o["keyword"].isin(keys)].pivot_table(index="bucket", columns="keyword", values="rank", aggfunc="mean").sort_index()
        day = org.groupby("crawl_date")["rank"].mean()
        facts = [f"Average organic rank moved from {dec(day.iat[0])} on {day.index[0]:%d %b} to {dec(day.iat[-1])} on "
                 f"{day.index[-1]:%d %b} ({'improved' if day.iat[-1] < day.iat[0] else 'slipped'} "
                 f"{abs(day.iat[-1] - day.iat[0]):.1f} positions)."]
        vol = piv.std().sort_values(ascending=False)
        if len(vol) and vol.iat[0] == vol.iat[0]:
            facts.append(f"Most volatile keyword: “{vol.index[0]}” (rank swings between {dec(piv[vol.index[0]].min())} and {dec(piv[vol.index[0]].max())}).")
        ch = chart("line", "Organic rank over time, 6-hour averages (lower is better)",
                   [f"{t:%d %b %H:%M}" for t in piv.index], None, "dec",
                   series={k: [None if v != v else float(v) for v in piv[k]] for k in keys if k in piv}, invert=True)
        sections.append(section("rank_trend", "Organic rank trend", facts, ch, None))

    # 3 paid vs organic
    dd = d.groupby("crawl_date").agg(apps=("rank", "size"), spons=("sponsored", "sum"), banner=("banner", "sum"),
                                     price=("price", "median"), lo=("price", "min"), hi=("price", "max"),
                                     mrp=("mrp", "median"), rc=("rating_count", "max"), rating=("rating", "mean"))
    dd["organic"] = dd["apps"] - dd["spons"]
    dd["org_rank"] = org.groupby("crawl_date")["rank"].mean()
    facts = [f"{pct(len(sp) / len(d) * 100)} of the product's search appearances are sponsored; "
             f"{pct(d['banner'].mean() * 100)} come from banner ad units.",
             f"{pct((d['page'] == 1).mean() * 100)} of appearances are on page 1."]
    labels = [f"{i:%d %b}" for i in dd.index]
    ch = chart("stacked", "Search appearances per day: organic vs sponsored", labels, None, "num",
               series={"Organic": dd["organic"].astype(float).tolist(), "Sponsored": dd["spons"].astype(float).tolist()})
    tb = table(["Day", "Appearances", "Sponsored", "Avg organic rank"],
               [[f"{i:%d %b %Y}", cnt(r.apps), pct(r.spons / r.apps * 100), dec(r.org_rank)] for i, r in dd.iterrows()], [2, 1, 1, 1.3])
    sections.append(section("paid_vs_organic", "Paid versus organic visibility", facts, ch, tb))

    # 4 price and offer
    lo, hi = d["price"].min(), d["price"].max()
    facts = [f"Selling price ranged from {money(lo)} to {money(hi)} during the period." if lo != hi else
             f"Selling price held at {money(lo)} throughout.",
             f"Rating held at {dec(d['rating'].mean())}★ with about {cnt(d['rating_count'].max())} ratings."]
    if lo != hi and len(dd) > 1:
        first, last = dd["price"].iat[0], dd["price"].iat[-1]
        if first != last:
            facts.append(f"Typical price moved from {money(first)} to {money(last)} between {dd.index[0]:%d %b} and {dd.index[-1]:%d %b}.")
    tb = table(["Day", "Lowest price", "Highest price", "MRP", "Rating", "Ratings"],
               [[f"{i:%d %b %Y}", money(r.lo), money(r.hi), money(r.mrp), dec(r.rating), cnt(r.rc)] for i, r in dd.iterrows()],
               [2, 1.2, 1.2, 1, 1, 1])
    sections.append(section("price_offer", "Price and offer tracking", facts, None, tb))

    return {
        "subject": trunc(title, 70), "scope": "; ".join(scope) or "All tracked keywords", "rows": len(d),
        "kpis": kpis, "sections": sections,
        "definitions": [
            "Rank: the product's position in Amazon search results for the keyword; lower is better.",
            "Organic vs sponsored: a result is sponsored when Amazon labels it as an ad placement.",
            "Appearance: one occurrence of the product in a search-results crawl (a product can appear several times per page).",
        ],
    }

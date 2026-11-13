"""Store-level availability of one product – from the Blinkit product-page crawl."""
from .base import (as_list, chart, cnt, field, join_names, kpi, money, opts, pct, section, table, top_n, trunc)

ID = "store_availability"
NAME = "Store-Level Availability"
DATASET = "product_details"
DESCRIPTION = ("Where a single product is actually buyable: in-stock rate across every dark store checked, "
               "city coverage, the stores that have it, price points seen and sellers.")
CHANNEL = "Blinkit"
SECTIONS = [
    ("city_coverage", "Coverage by city", "Stores checked and in stock per city"),
    ("in_stock_stores", "Stores with stock", "The individual stores where the product is buyable"),
    ("price_points", "Price points seen", "Selling prices and discounts across stores"),
    ("sellers", "Sellers", "Seller entities behind the listings"),
]
KEYWORDS = ["store", "dark store", "store level", "where", "buyable", "single product", "sku availability",
            "stock-out", "stockout", "coverage", "distribution", "merchant", "seller"]
ENTITY_FIELD = "product"


def fields(df):
    pr = df.groupby("sku").agg(title=("title", "first"), n=("sku", "size")).sort_values("n", ascending=False)
    c = df.groupby(["sku", "city"]).size().reset_index(name="n").sort_values("n", ascending=False)
    return [
        field("product", "Product", "select", True,
              opts(pr.index, [f"{trunc(t, 62)} ({s})" for s, t in pr["title"].items()]), "The product to audit."),
        field("cities", "Cities", "multi", False, opts(c["city"], parents=c["sku"]),
              "Leave empty for every city crawled.", "product"),
    ]


def build(df, p):
    n = top_n(p)
    d = df[df["sku"] == p["product"]]
    scope = []
    if as_list(p.get("cities")):
        d = d[d["city"].isin(as_list(p["cities"]))]
        scope.append("cities: " + ", ".join(as_list(p["cities"])))
    if d.empty:
        raise ValueError("No rows match that product / city combination.")
    title = d["title"].iloc[0]
    # one row per store: the latest check wins
    s = d.sort_values("crawl_time").groupby("store_id").tail(1)
    live = s[s["in_stock"]]
    avail = len(live) / len(s) * 100
    priced = s[s["price"].notna()]

    kpis = [
        kpi("Stores checked", cnt(len(s)), f"{s['city'].nunique()} cities"),
        kpi("Stores in stock", cnt(len(live))),
        kpi("In-stock rate", pct(avail, 1)),
        kpi("Stores showing a price", cnt(len(priced)), pct(len(priced) / len(s) * 100) + " of stores"),
        kpi("Price range", f"{money(priced['price'].min())}–{money(priced['price'].max())}" if len(priced) else "–",
            f"MRP {money(priced['mrp'].max())}" if len(priced) else ""),
        kpi("Sellers", cnt(s["merchant"].nunique())),
    ]
    sections = []

    # 1 city coverage
    c = s.groupby("city").agg(stores=("store_id", "size"), live=("in_stock", "sum"), priced=("price", "count"))
    c["avail"] = c["live"] / c["stores"] * 100
    c = c.sort_values("stores", ascending=False)
    zero = c[c["live"] == 0]
    facts = [f"{trunc(title, 70)} is in stock in {len(live)} of {cnt(len(s))} stores checked ({pct(avail, 1)}).",
             f"{len(zero)} of {len(c)} cities have no store with stock, including {join_names(zero.index[:4], 4)}." if len(zero) else
             "Every city has at least one store with stock.",
             (f"Stock was found only in {join_names(c[c['live'] > 0].index, 5)}." if 0 < (c["live"] > 0).sum() <= 5 else "")]
    t = c.head(max(n, 12))
    ch = chart("barh", "Stores checked by city", t.index, t["stores"], "num")
    tb = table(["City", "Stores checked", "In stock", "In-stock rate", "Showing a price"],
               [[i, cnt(r.stores), cnt(r.live), pct(r.avail, 1), cnt(r.priced)] for i, r in t.iterrows()], [2.2, 1.3, 1, 1.2, 1.4])
    sections.append(section("city_coverage", "Coverage by city", facts, ch, tb))

    # 2 where it is available
    if len(live):
        lo, hi = live["price"].min(), live["price"].max()
        facts = [f"In-stock stores sell at {money(lo) if lo == hi else money(lo) + '–' + money(hi)}"
                 + (f" against an MRP of {money(live['mrp'].max())}." if live["mrp"].notna().any() else ".")]
        tb = table(["City", "Store ID", "Price", "MRP", "Discount", "Seller"],
                   [[r.city, r.store_id, money(r.price), money(r.mrp), pct(r.discount), trunc(r.merchant, 34)]
                    for r in live.sort_values("city").head(25).itertuples()], [1.6, 1, 0.9, 0.9, 1, 3.2])
        sections.append(section("in_stock_stores", "Stores with stock", facts, None, tb))

    # 3 price points
    if len(priced):
        pp = priced.groupby("price").agg(stores=("store_id", "size"), mrp=("mrp", "max"), disc=("discount", "mean"),
                                         live=("in_stock", "sum")).sort_values("stores", ascending=False)
        facts = [f"{len(pp)} distinct price point(s) were seen across {len(priced)} stores; the most common is "
                 f"{money(pp.index[0])} ({pct(pp['stores'].iat[0] / len(priced) * 100)} of priced stores).",
                 f"Discounts run from {pct(priced['discount'].min())} to {pct(priced['discount'].max())} off MRP."
                 if priced["discount"].notna().any() else ""]
        o = pp.sort_index()
        ch = chart("bar", "Stores by price point", [money(i) for i in o.index], o["stores"], "num") if len(pp) > 1 else None
        tb = table(["Price", "MRP", "Discount", "Stores", "Of which in stock"],
                   [[money(i), money(r.mrp), pct(r.disc), cnt(r.stores), cnt(r.live)] for i, r in pp.iterrows()], [1, 1, 1, 1, 1.4])
        sections.append(section("price_points", "Price points seen", facts, ch, tb))

    # 4 sellers
    m = s.dropna(subset=["merchant"]).groupby("merchant").agg(stores=("store_id", "size"), live=("in_stock", "sum"),
                                                              price=("price", "median")).sort_values("stores", ascending=False)
    if len(m):
        facts = [f"{len(m)} seller entities were identified; {m.index[0]} covers the most stores ({m['stores'].iat[0]}).",
                 f"Seller information is visible for {pct(s['merchant'].notna().mean() * 100, 1)} of stores."]
        tb = table(["Seller", "Stores", "In stock", "Median price"],
                   [[trunc(i, 50), cnt(r.stores), cnt(r.live), money(r.price)] for i, r in m.head(n).iterrows()], [4, 1, 1, 1.2])
        sections.append(section("sellers", "Sellers", facts, None, tb))

    return {
        "subject": trunc(title, 70), "scope": "; ".join(scope) or "All stores crawled", "rows": len(d),
        "kpis": kpis, "sections": sections,
        "definitions": [
            "In-stock rate: share of stores where the product page showed the item as available (latest check per store).",
            "Showing a price: stores where the product page returned a selling price, in stock or not.",
            "City: derived from store coordinates (nearest major city).",
        ],
    }

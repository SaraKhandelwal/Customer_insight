"""Builds one static HTML report per CSV in data/ and writes them to docs/.

File naming in data/:
    Brand Name.csv                      -> report for that brand
    Brand Name__vs__Rival Name.csv      -> report with a competitor comparison
                                           (rival reviews go in a second file, see README)
Prefix a file name with "SAMPLE " to stamp the report as demo data.

Run:  python build_reports.py
"""
import html
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import analysis as A

DATA, OUT = Path("data"), Path("docs")
GOOD, BAD, INK, MUTED = "#0F766E", "#B4432F", "#1F2A44", "#9AA3B5"
PLOTLY_JS = "https://cdn.plot.ly/plotly-2.35.2.min.js"

# Edit this block: it appears at the bottom of every report.
CONTACT = {
    "name": "Sara Khandelwal",
    "line": "Purdue business analytics senior, graduating in May, looking for analyst roles in New York.",
    "email": "khande23@purdue.edu",
    "linkedin": "https://www.linkedin.com/in/khande",
}

CSS = """
:root{--ink:#1F2A44;--muted:#5B6578;--line:#E3E7EF;--soft:#F4F6FA;--good:#0F766E;--bad:#B4432F;--bg:#fff}
@media (prefers-color-scheme:dark){:root{--ink:#E8ECF5;--muted:#A3ACBF;--line:#2B3347;--soft:#1A2030;--bg:#0F1420}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:2rem 1.2rem 4rem}
h1{font-size:2rem;line-height:1.2;margin:.2rem 0 .4rem}
h2{font-size:1.25rem;margin:2.4rem 0 .8rem}
.sub{color:var(--muted);margin:0 0 1.4rem}
.banner{background:#FFF4D6;color:#5A4300;padding:.6rem .9rem;border-radius:6px;margin-bottom:1rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.8rem}
.kpi{background:var(--soft);border-radius:8px;padding:.9rem 1rem}
.kpi b{display:block;font-size:1.7rem}
.kpi span{color:var(--muted);font-size:.9rem}
.rec{background:var(--soft);border-radius:8px;padding:.8rem 1rem;margin:.6rem 0}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.4rem}
details{border-bottom:1px solid var(--line);padding:.5rem 0}
summary{cursor:pointer;font-weight:600}
q{display:block;border-left:3px solid var(--bad);padding:.1rem .7rem;margin:.4rem 0;color:var(--muted);quotes:none}
q.good{border-left-color:var(--good)}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);color:var(--muted)}
footer a{color:inherit}
.chart{overflow-x:auto}
"""


def fig_html(fig, height):
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.12))
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def quotes(sent, theme, negative):
    cls = "" if negative else " class='good'"
    return "".join(f"<q{cls}>{html.escape(q)}</q>" for q in A.top_quotes(sent, theme, negative))


def build(brand, df, rival_name=None, rival_df=None, sample=False):
    rev = A.load_reviews(df)
    sent = A.sentence_table(rev)
    themes = A.theme_summary(sent)
    r_themes = None
    if rival_df is not None:
        r_themes = A.theme_summary(A.sentence_table(A.load_reviews(rival_df)))

    dates = rev["date"].dropna()
    span = f"{dates.min():%b %Y} to {dates.max():%b %Y}" if len(dates) else "all dates"
    if rev["rating"].notna().any():
        third = f"<b>{rev['rating'].mean():.2f} / 5</b><span>Average rating</span>"
    else:
        third = f"<b>{rev['sentiment'].mean():+.2f}</b><span>Average sentiment</span>"
    kpis = (f"<div class='kpi'><b>{(rev['label'] == 'Positive').mean() * 100:.0f}%</b><span>Positive reviews</span></div>"
            f"<div class='kpi'><b>{(rev['label'] == 'Negative').mean() * 100:.0f}%</b><span>Negative reviews</span></div>"
            f"<div class='kpi'>{third}</div>")

    recs = "".join(f"<div class='rec'>{html.escape(r)}</div>"
                   for r in A.recommendations(brand, rev, sent, themes, r_themes, rival_name))

    body = ""
    trend = A.monthly_trend(rev)
    if len(trend) > 1:
        f = go.Figure()
        f.add_bar(x=trend["month"], y=trend["reviews"], name="Reviews", marker_color="#C9D0E0", yaxis="y2")
        f.add_scatter(x=trend["month"], y=trend["avg_sentiment"], name="Average sentiment",
                      line=dict(color=GOOD, width=3))
        f.update_layout(yaxis=dict(title="Sentiment (-1 to +1)", range=[-1, 1]),
                        yaxis2=dict(overlaying="y", side="right", showgrid=False, title="Reviews"))
        body += f"<h2>Sentiment over time</h2><div class='chart'>{fig_html(f, 320)}</div>"

    if not themes.empty:
        t = themes.sort_values("mentions")
        f = go.Figure()
        f.add_bar(y=t["theme"], x=t["positive"], name="Positive", orientation="h", marker_color=GOOD)
        f.add_bar(y=t["theme"], x=-t["negative"], name="Negative", orientation="h", marker_color=BAD)
        f.update_layout(barmode="relative", xaxis_title="Mentions")
        body += f"<h2>What customers love and complain about</h2><div class='chart'>{fig_html(f, 40 * len(t) + 120)}</div>"
        loves = themes.sort_values("positive", ascending=False).head(5)
        gripes = themes.sort_values("negative", ascending=False).head(5)
        l = "".join(f"<details><summary>{html.escape(r.theme)} ({r.positive} positive)</summary>"
                    f"{quotes(sent, r.theme, False)}</details>" for r in loves.itertuples())
        g = "".join(f"<details><summary>{html.escape(r.theme)} ({r.negative} negative)</summary>"
                    f"{quotes(sent, r.theme, True)}</details>" for r in gripes.itertuples())
        body += f"<div class='cols'><div><h2>Top 5 loves</h2>{l}</div><div><h2>Top 5 complaints</h2>{g}</div></div>"

    if r_themes is not None and not r_themes.empty and not themes.empty:
        m = themes.merge(r_themes, on="theme", suffixes=("", "_r")).sort_values("pct_negative_r")
        f = go.Figure()
        f.add_bar(y=m["theme"], x=m["pct_negative"], name=brand, orientation="h", marker_color=GOOD)
        f.add_bar(y=m["theme"], x=m["pct_negative_r"], name=rival_name, orientation="h", marker_color=MUTED)
        f.update_layout(barmode="group", xaxis_title="% of mentions that are negative (lower is better)")
        body += (f"<h2>{html.escape(brand)} vs {html.escape(rival_name)}</h2>"
                 f"<div class='chart'>{fig_html(f, 60 * len(m) + 120)}</div>")

    banner = "<div class='banner'>Sample report built on synthetic demo data.</div>" if sample else ""
    c = CONTACT
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Customer Voice Report: {html.escape(brand)}</title>
<script src="{PLOTLY_JS}"></script><style>{CSS}</style></head><body><main>
{banner}<h1>What {html.escape(brand)} customers are saying</h1>
<p class="sub">Based on {len(rev):,} public reviews, {span}. Sentiment is scored with VADER and themes are matched sentence by sentence.</p>
<div class="kpis">{kpis}</div>
<h2>What to do about it</h2>{recs}{body}
<footer><p>Built from public customer reviews only. No private company data was used.</p>
<p><b>{html.escape(c['name'])}</b>. {html.escape(c['line'])}
<a href="mailto:{c['email']}">{c['email']}</a> | <a href="{c['linkedin']}">LinkedIn</a></p></footer>
</main></body></html>"""


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    OUT.mkdir(exist_ok=True)
    made = []
    for f in sorted(DATA.glob("*.csv")):
        stem = f.stem
        if "__vs__" in stem:
            continue  # handled with its brand file below
        sample = stem.upper().startswith("SAMPLE ")
        brand = stem[7:] if sample else stem
        rival = next(iter(DATA.glob(f"{stem}__vs__*.csv")), None)
        rival_name = rival.stem.split("__vs__", 1)[1] if rival else None
        try:
            page = build(brand, pd.read_csv(f), rival_name, pd.read_csv(rival) if rival else None, sample)
        except Exception as e:
            print(f"SKIPPED {f.name}: {e}")
            continue
        (OUT / f"{slug(brand)}.html").write_text(page, encoding="utf-8")
        made.append(f"{slug(brand)}.html")
        print(f"built docs/{slug(brand)}.html")
    (OUT / "index.html").write_text("<!doctype html><meta charset='utf-8'><meta name='robots' content='noindex'>"
                                    "<title>Customer Voice Report</title>", encoding="utf-8")
    if not made:
        print("No reports built. Put CSV files in data/ (see README).")


if __name__ == "__main__":
    main()

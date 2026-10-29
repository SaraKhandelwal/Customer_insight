"""Core analysis for the Customer Voice Report.

Takes a table of public customer reviews and returns sentiment, themes,
trends and plain-English recommendations. Theme detection works at the
sentence level, so a review like "Love the scent, but shipping was slow"
is credited correctly on both topics.
"""
import re

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_sia = SentimentIntensityAnalyzer()

THEMES = {
    "Shipping & delivery": ["ship", "deliver", "arriv", "courier", "tracking", "delay", "late"],
    "Packaging": ["packag", "box", "bottle", "seal", "leak", "wrap", "container", "jar"],
    "Price & value": ["price", "expens", "cheap", "value", "worth", "cost", "overpriced", "afford"],
    "Quality": ["quality", "durab", "broke", "flimsy", "well made", "defect", "fell apart", "cheaply"],
    "Customer service": ["service", "support", "refund", "return", "exchange", "respond", "rude", "staff"],
    "Taste, scent & texture": ["taste", "flavor", "scent", "smell", "fragrance", "texture", "sweet",
                               "bitter", "creamy", "greasy", "sticky"],
    "Results & effectiveness": ["work", "result", "effective", "difference", "noticed", "improv", "clear"],
    "Size & fit": ["size", " fit", "fits", "runs small", "runs large", "tight", "loose"],
    "Website & ordering": ["website", "checkout", "app ", "login", "order", "subscription", "cancel"],
}
_PATTERNS = {t: re.compile(r"(?:^|\W)(?:" + "|".join(re.escape(k.strip()) for k in kws) + ")", re.I)
             for t, kws in THEMES.items()}

TEXT_COLS = ["review", "text", "body", "content", "review_text", "comment"]
DATE_COLS = ["date", "review_date", "created_at", "time", "reviewed_at"]
RATING_COLS = ["rating", "stars", "score", "star_rating"]


def _pick(df, options):
    lower = {c.lower().strip(): c for c in df.columns}
    for o in options:
        if o in lower:
            return lower[o]
    return None


def load_reviews(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize any reasonable review CSV into: text, date, rating."""
    text_col = _pick(raw, TEXT_COLS)
    if text_col is None:
        raise ValueError("Could not find a review text column. Name it 'review' or 'text'.")
    out = pd.DataFrame({"text": raw[text_col].astype(str)})
    date_col, rating_col = _pick(raw, DATE_COLS), _pick(raw, RATING_COLS)
    out["date"] = pd.to_datetime(raw[date_col], errors="coerce") if date_col else pd.NaT
    out["rating"] = pd.to_numeric(raw[rating_col], errors="coerce") if rating_col else float("nan")
    out = out[out["text"].str.strip().str.len() > 3].reset_index(drop=True)
    out["review_id"] = out.index
    out["sentiment"] = out["text"].map(lambda t: _sia.polarity_scores(t)["compound"])
    out["label"] = pd.cut(out["sentiment"], [-1.01, -0.05, 0.05, 1.01],
                          labels=["Negative", "Neutral", "Positive"])
    return out


def sentence_table(reviews: pd.DataFrame) -> pd.DataFrame:
    """One row per (sentence, theme) match, with sentence-level sentiment."""
    rows = []
    for r in reviews.itertuples():
        for s in re.split(r"(?<=[.!?])\s+", r.text):
            s = s.strip()
            if len(s) < 8:
                continue
            hits = [t for t, p in _PATTERNS.items() if p.search(s)]
            if hits:
                score = _sia.polarity_scores(s)["compound"]
                rows += [{"review_id": r.review_id, "date": r.date, "theme": t,
                          "sentence": s, "sentiment": score} for t in hits]
    cols = ["review_id", "date", "theme", "sentence", "sentiment"]
    return pd.DataFrame(rows, columns=cols)


def theme_summary(sent: pd.DataFrame, thresh: float = 0.25) -> pd.DataFrame:
    if sent.empty:
        return pd.DataFrame(columns=["theme", "mentions", "positive", "negative", "net", "pct_negative"])
    g = sent.groupby("theme")["sentiment"]
    out = pd.DataFrame({
        "mentions": g.size(),
        "positive": g.apply(lambda s: int((s >= thresh).sum())),
        "negative": g.apply(lambda s: int((s <= -thresh).sum())),
    })
    out["net"] = out["positive"] - out["negative"]
    out["pct_negative"] = (out["negative"] / out["mentions"] * 100).round(0)
    return out.reset_index().sort_values("mentions", ascending=False)


def monthly_trend(reviews: pd.DataFrame) -> pd.DataFrame:
    d = reviews.dropna(subset=["date"])
    if d.empty:
        return pd.DataFrame(columns=["month", "avg_sentiment", "reviews"])
    m = d.groupby(d["date"].dt.to_period("M").dt.to_timestamp()).agg(
        avg_sentiment=("sentiment", "mean"), reviews=("sentiment", "size")).reset_index()
    return m.rename(columns={"date": "month"})


def top_quotes(sent: pd.DataFrame, theme: str, negative: bool, n: int = 3):
    d = sent[sent["theme"] == theme].sort_values("sentiment", ascending=negative)
    return [q[:220] for q in d["sentence"].head(n)]


def complaint_shift(sent: pd.DataFrame, days: int = 90, thresh: float = 0.25):
    """Compare negative mentions per theme: last N days vs the N days before."""
    d = sent.dropna(subset=["date"])
    if d.empty:
        return pd.DataFrame(columns=["theme", "recent", "prior", "change"])
    end = d["date"].max()
    neg = d[d["sentiment"] <= -thresh]
    recent = neg[neg["date"] > end - pd.Timedelta(days=days)].groupby("theme").size()
    prior = neg[(neg["date"] <= end - pd.Timedelta(days=days)) &
                (neg["date"] > end - pd.Timedelta(days=2 * days))].groupby("theme").size()
    out = pd.DataFrame({"recent": recent, "prior": prior}).fillna(0).astype(int)
    out["change"] = out["recent"] - out["prior"]
    return out.reset_index().rename(columns={"index": "theme"}).sort_values("change", ascending=False)


def recommendations(brand, reviews, sent, themes, rival_themes=None, rival_name=None):
    recs = []
    if themes.empty:
        return ["Not enough theme data yet. Add more reviews (200+ works best)."]
    worst = themes.sort_values("negative", ascending=False).iloc[0]
    recs.append(f"Fix first: {worst['theme']}. It has the most complaints for {brand} "
                f"({int(worst['negative'])} negative mentions, {int(worst['pct_negative'])}% of everything "
                f"customers say about it).")
    shift = complaint_shift(sent)
    if not shift.empty and shift.iloc[0]["change"] >= 3:
        s = shift.iloc[0]
        recs.append(f"Watch this: complaints about {s['theme'].lower()} rose from {int(s['prior'])} to "
                    f"{int(s['recent'])} in the last 90 days. Something changed recently, and it is worth "
                    f"finding out what.")
    best = themes.sort_values("positive", ascending=False).iloc[0]
    recs.append(f"Say it louder: customers love {best['theme'].lower()} ({int(best['positive'])} positive "
                f"mentions). Use their own words in ads and on the product page.")
    if rival_themes is not None and not rival_themes.empty:
        m = themes.merge(rival_themes, on="theme", suffixes=("", "_r"))
        m["gap"] = m["pct_negative"] - m["pct_negative_r"]
        if not m.empty:
            g = m.sort_values("gap", ascending=False).iloc[0]
            if g["gap"] > 0:
                recs.append(f"Gap vs {rival_name}: on {g['theme'].lower()}, {int(g['pct_negative'])}% of "
                            f"mentions are negative for {brand} versus {int(g['pct_negative_r'])}% for "
                            f"{rival_name}. That is where customers are being lost.")
    return recs

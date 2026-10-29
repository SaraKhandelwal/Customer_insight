# Customer Voice Report

Turns public customer reviews into a one-page web report per brand: sentiment over time, what customers
love, what they complain about, a competitor comparison, and plain-English recommendations.

## How it works
1. Put review CSVs in `data/`.
2. Push to GitHub. A GitHub Action builds one web page per CSV and publishes them.
3. Each brand gets its own link: `https://YOUR-USERNAME.github.io/REPO-NAME/brand-name.html`

## CSV format
One review per row. Columns: `review` (required), `date` and `rating` (optional, but dates unlock the trend chart).
Aim for 200+ reviews per brand.

## File names in data/
- `Glossier.csv` builds a report for Glossier.
- `Glossier__vs__Ilia.csv` adds a competitor comparison (this file holds the competitor's reviews).
- Start a name with `SAMPLE ` to stamp the report as demo data.

## One-time setup
1. Create a PUBLIC GitHub repo and push this folder. (Free GitHub Pages needs a public repo, so the CSVs are public too.)
2. In the repo: Settings, Pages, Source: GitHub Actions.
3. Push any change. The Actions tab shows the build, and the link appears when it finishes.

## Run locally
    pip install -r requirements.txt
    python build_reports.py
Then open the files in `docs/`.

## Before sending a link
Edit the CONTACT block at the top of `build_reports.py`. Delete the SAMPLE files once you have real ones.
Reports include a no-index tag, but anyone with the link can open it.

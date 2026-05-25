#!/usr/bin/env python3
"""
generate_earnings_charts.py — Find recent earnings filings and generate charts.

Checks SEC EDGAR for 10-Q/10-K filings from the last 2 days for watchlist tickers.
Saves charts to images/earnings/ and writes a manifest for the posting step.

Set FORCE_TICKERS=NVDA,AAPL to skip the EDGAR check and force specific tickers.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from sec_trend_chart import (
    fetch_facts, build_trend, build_figure, apply_rounded_header,
    load_logo, load_brand_logo, fmt_money, pct_chg, C, DPI,
)

UA         = {"User-Agent": "StockScore App sahidkhan@live.co.uk"}
ROOT       = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "images" / "earnings"
MANIFEST   = Path(__file__).parent / "_post_manifest.json"

def _load_watchlist() -> list[str]:
    path = Path(__file__).parent / "watchlist.yml"
    with path.open() as f:
        return [t.upper() for t in yaml.safe_load(f)["tickers"]]

WATCHLIST = _load_watchlist()


def fetch_ticker_map() -> dict:
    """Download SEC's full ticker→CIK mapping once (avoids 40 individual lookups)."""
    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=UA, timeout=15,
    )
    r.raise_for_status()
    return {
        e["ticker"].upper(): (str(e["cik_str"]).zfill(10), e["title"])
        for e in r.json().values()
    }


def check_recent_filing(cik: str, days: int = 2) -> str | None:
    """Return '10-Q' or '10-K' if company filed one within `days` days, else None."""
    r = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers=UA, timeout=15,
    )
    r.raise_for_status()
    recent = r.json().get("filings", {}).get("recent", {})
    forms  = recent.get("form", [])
    dates  = recent.get("filingDate", [])
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)

    for form, date_str in zip(forms, dates):
        if form not in ("10-Q", "10-K"):
            continue
        try:
            if datetime.strptime(date_str, "%Y-%m-%d").date() >= cutoff:
                return form
        except ValueError:
            continue
    return None


def generate_chart(ticker: str, cik: str, company: str, out_path: Path) -> list | None:
    """Fetch EDGAR facts, render chart to out_path. Returns quarters list or None."""
    try:
        facts    = fetch_facts(cik)
        quarters = build_trend(facts, 8)
        if len(quarters) < 2:
            print(f"  fewer than 2 quarters found — skipping")
            return None
        co_logo = load_logo(ticker)
        br_logo = load_brand_logo()
        fig = build_figure(quarters, company, ticker, co_logo, br_logo)
        fig.savefig(str(out_path), dpi=DPI, facecolor=C["bg"])
        plt.close(fig)
        apply_rounded_header(str(out_path))
        return quarters
    except Exception as e:
        print(f"  chart generation failed: {e}")
        return None


def caption_data(ticker: str, company: str, quarters: list) -> dict:
    """Extract metrics needed to build the social media caption."""
    latest = quarters[-1]
    yoy_q  = quarters[-5] if len(quarters) >= 5 else None
    rev    = latest["revenue"]
    ni     = latest["net_income"]
    gp     = latest["gross_profit"]
    return {
        "ticker":      ticker,
        "company":     company,
        "label":       latest["label"].replace("\n", " "),
        "revenue":     fmt_money(rev),
        "net_income":  fmt_money(ni),
        "rev_yoy_pct": pct_chg(rev, yoy_q["revenue"]    if yoy_q else None),
        "ni_yoy_pct":  pct_chg(ni,  yoy_q["net_income"] if yoy_q else None),
        "gm_pct":      (gp / rev * 100) if (gp and rev) else None,
        "nm_pct":      (ni / rev * 100) if (ni and rev) else None,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    force_env = os.environ.get("FORCE_TICKERS", "").strip()
    if force_env:
        tickers         = [t.strip().upper() for t in force_env.split(",") if t.strip()]
        skip_edgar_check = True
        print(f"Force mode — processing: {tickers}")
    else:
        tickers         = WATCHLIST
        skip_edgar_check = False
        print(f"Checking {len(tickers)} watchlist tickers for recent earnings filings...")

    print("Fetching SEC ticker→CIK map...")
    try:
        ticker_map = fetch_ticker_map()
    except Exception as e:
        print(f"ERROR: could not fetch ticker map: {e}")
        sys.exit(1)

    manifest = []

    for ticker in tickers:
        print(f"\n[{ticker}]")

        entry = ticker_map.get(ticker)
        if not entry:
            print(f"  not found in SEC ticker map — skipping")
            continue
        cik, company = entry

        if not skip_edgar_check:
            form = check_recent_filing(cik, days=2)
            if not form:
                print(f"  no recent 10-Q/10-K — skipping")
                time.sleep(0.2)
                continue
            print(f"  recent {form} found for {company}")

        out_path = OUTPUT_DIR / f"{ticker}_trend.png"
        quarters = generate_chart(ticker, cik, company, out_path)
        if quarters is None:
            continue

        print(f"  chart saved → {out_path.name}")
        manifest.append(caption_data(ticker, company, quarters))
        time.sleep(1)  # keep EDGAR happy

    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    if manifest:
        print(f"\n{len(manifest)} chart(s) generated: {[m['ticker'] for m in manifest]}")
    else:
        print("\nNo recent earnings filings found for watchlist tickers.")


if __name__ == "__main__":
    main()

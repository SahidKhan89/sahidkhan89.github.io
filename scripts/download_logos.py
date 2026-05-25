#!/usr/bin/env python3
"""
download_logos.py — Fetch company logos for all watchlist tickers.

Saves PNG files to repo-root/logos/<TICKER>.png.
Run once locally and commit the logos/ directory to the repo.

Usage:
    python scripts/download_logos.py           # all watchlist tickers
    python scripts/download_logos.py NVDA AAPL # specific tickers only
"""

import sys
import time
from pathlib import Path

import requests
import yaml

LOGO_DIR = Path(__file__).parent.parent / "logos"
WATCHLIST_FILE = Path(__file__).parent / "watchlist.yml"


def download_logo(ticker: str) -> bool:
    out = LOGO_DIR / f"{ticker}.png"
    if out.exists():
        print(f"  [{ticker}] already exists — skipping")
        return True

    url = f"https://financialmodelingprep.com/image-stock/{ticker}.png"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
            out.write_bytes(resp.content)
            print(f"  [{ticker}] saved ({len(resp.content):,} bytes)")
            return True
        else:
            print(f"  [{ticker}] not found (HTTP {resp.status_code})")
            return False
    except Exception as e:
        print(f"  [{ticker}] error: {e}")
        return False


def main():
    LOGO_DIR.mkdir(exist_ok=True)

    if len(sys.argv) > 1:
        tickers = [t.upper() for t in sys.argv[1:]]
    else:
        with open(WATCHLIST_FILE) as f:
            tickers = [t.upper() for t in yaml.safe_load(f)["tickers"]]

    print(f"Fetching logos for {len(tickers)} ticker(s)...\n")

    ok = failed = 0
    for i, ticker in enumerate(tickers):
        result = download_logo(ticker)
        if result:
            ok += 1
        else:
            failed += 1
        if i < len(tickers) - 1:
            time.sleep(0.2)

    print(f"\nDone — {ok} saved, {failed} failed.")
    print(f"Logos written to: {LOGO_DIR}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
debug_sector_heatmap_data.py — TEMPORARY diagnostic for the sector heatmap
posting one session stale in the evening.

At the moment it runs, logs:
  1. yf.download(period='5d') exactly as the backend calls it: bar dates,
     last closes, and the % change the backend's _pct() would produce.
  2. Yahoo's raw chart API for a couple of tickers: bar timestamps plus meta
     (regularMarketTime, regularMarketPrice, chartPreviousClose).
  3. The live backend /sector-heatmap response, matched against the per-date
     % changes so we can see which session it's actually serving.
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

BACKEND_URL = os.environ.get("BACKEND_URL", "https://disturbed-melly-skhan89-05036d6c.koyeb.app")
TICKERS     = ["XLK", "XLV", "XLF", "XLE", "XLU", "SOXX", "GDX", "OIH"]
RAW_TICKERS = ["XLK", "GDX"]


def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def backend_pct(prices):
    """Same as routes/sector_heatmap.py _pct()."""
    if len(prices) < 2:
        return 0.0
    prev, curr = float(prices.iloc[-2]), float(prices.iloc[-1])
    return 0.0 if prev == 0 else round((curr - prev) / prev * 100, 2)


def main():
    now = datetime.now(timezone.utc)
    section("Run time")
    print(f"UTC:      {now:%Y-%m-%d %H:%M:%S}")
    print(f"New York: {now.astimezone(ZoneInfo('America/New_York')):%Y-%m-%d %H:%M:%S %Z}")
    print(f"yfinance: {yf.__version__}")

    section("1. yf.download(period='5d') — same call as the backend")
    data  = yf.download(" ".join(TICKERS), period="5d", progress=False, auto_adjust=True, threads=4)
    close = data["Close"]
    print(f"index: {[str(i) for i in close.index]}")
    print(close.round(2).to_string())
    print("\nper-ticker: last two bar dates used by _pct() → result")
    for t in TICKERS:
        s = close[t].dropna()
        print(f"  {t:5} {[d.strftime('%Y-%m-%d') for d in s.index[-2:]]} → {backend_pct(s):+.2f}%")

    # Reference % changes per session, for matching the backend's numbers below
    ref = yf.download(" ".join(TICKERS), period="1mo", progress=False, auto_adjust=True)["Close"]
    ref_pct = (ref.pct_change(fill_method=None) * 100).round(2)

    section("2. Yahoo chart meta via Ticker.history(period='5d')")
    for t in RAW_TICKERS:
        try:
            tk   = yf.Ticker(t)
            hist = tk.history(period="5d", auto_adjust=True)
            meta = tk.history_metadata
            print(f"{t}: bars {[d.strftime('%Y-%m-%d') for d in hist.index]}")
            print(f"  closes: {[round(c, 2) for c in hist['Close']]}")
            for k in ("regularMarketTime", "regularMarketPrice", "chartPreviousClose", "previousClose"):
                v = meta.get(k)
                if k == "regularMarketTime" and v:
                    v = f"{v} ({datetime.fromtimestamp(v, timezone.utc):%Y-%m-%d %H:%M UTC})"
                print(f"  meta.{k}: {v}")
        except Exception as e:
            print(f"{t}: failed — {e}")

    section("3. Backend /sector-heatmap — which session is it serving?")
    try:
        r = requests.get(f"{BACKEND_URL}/sector-heatmap", timeout=60)
        print(f"HTTP {r.status_code}, date header: {r.headers.get('date')}")
        served = {}
        for s in r.json().get("sectors", []):
            served[s["etf"]] = s["change_pct"]
            for i in s.get("industries", []):
                served[i["etf"]] = i["change_pct"]
        for t in TICKERS:
            v = served.get(t)
            matches = [d.strftime("%a %Y-%m-%d") for d, p in ref_pct[t].dropna().items() if abs(p - v) <= 0.01] if v is not None else []
            live = backend_pct(close[t].dropna())
            print(f"  {t:5} backend {v:+.2f}%  (this run's _pct: {live:+.2f}%)  "
                  f"matches session(s): {matches or 'none (live/intraday?)'}")
    except Exception as e:
        print(f"backend failed — {e}")


if __name__ == "__main__":
    main()

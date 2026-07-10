#!/usr/bin/env python3
"""
logos.py — shared ticker-logo fetch/load helpers.

Logos are cached on disk in logos/ (repo root) as {TICKER}.png, downloaded from
Financial Modeling Prep on first use. Used by the earnings-calendar,
analyst-ratings and dividends-calendar card generators.
"""

from pathlib import Path

import requests
from PIL import Image

ROOT     = Path(__file__).parent.parent
LOGO_DIR = ROOT / "logos"


def fetch_logo(ticker: str) -> None:
    """Download logo from FMP into logos/ if not already cached."""
    LOGO_DIR.mkdir(exist_ok=True)
    out = LOGO_DIR / f"{ticker}.png"
    if out.exists():
        return
    try:
        r = requests.get(
            f"https://financialmodelingprep.com/image-stock/{ticker}.png",
            timeout=10,
        )
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            out.write_bytes(r.content)
        else:
            print(f"  no logo found for {ticker} (HTTP {r.status_code})")
    except Exception as e:
        print(f"  logo download failed for {ticker}: {e}")


def load_logo_pil(ticker: str) -> Image.Image | None:
    """Load a cached logo as an RGBA PIL Image, fetching it first if needed."""
    fetch_logo(ticker)
    for nm in (f"{ticker}.png", f"{ticker}.jpg", f"{ticker}.F.png"):
        p = LOGO_DIR / nm
        if p.exists():
            try:
                return Image.open(p).convert("RGBA")
            except Exception:
                return None
    return None

#!/usr/bin/env python3
"""
generate_earnings_charts.py — Find recent earnings filings and generate charts.

Checks SEC EDGAR for 10-Q/10-K filings from the last 2 days for watchlist tickers.
Saves charts to images/earnings/ and writes a manifest for the posting step.

Set FORCE_TICKERS=NVDA,AAPL to skip the EDGAR check and force specific tickers.
"""

import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from sec_trend_chart import (
    fetch_facts, build_trend, build_figure, apply_rounded_header,
    load_logo, load_brand_logo, fmt_money, pct_chg, quarter_label, C, DPI,
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


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.current, self.row, self.cell, self.depth = [], [], [], '', 0
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.depth += 1; self.current = [] if self.depth == 1 else self.current
        elif tag == 'tr' and self.depth: self.row = []
        elif tag in ('td', 'th') and self.depth: self.cell = ''
    def handle_endtag(self, tag):
        if tag == 'table':
            self.depth -= 1
            if self.depth == 0: self.tables.append(self.current); self.current = []
        elif tag == 'tr' and self.depth:
            if any(c.strip() for c in self.row): self.current.append(self.row)
        elif tag in ('td', 'th') and self.depth: self.row.append(self.cell.strip()); self.cell = ''
    def handle_data(self, d):
        if self.depth: self.cell += d


def _fetch_text(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try: return r.content.decode(enc)
        except: pass
    return r.content.decode('utf-8', errors='replace')


def _detect_scale(html: str) -> float:
    """Fallback only, used when there's no prior-quarter revenue to check
    magnitude against (see fetch_8k_extras). Earnings-release exhibits often
    mix units across tables (financials in millions, guidance in billions, a
    per-share footnote in thousands), so a document-wide phrase search isn't
    reliable enough to use as the primary signal — it previously caused
    revenue to be parsed 1000x too small whenever any *other* table in the
    same document happened to say "in thousands"."""
    lower = html.lower()
    if 'in thousands' in lower: return 0.001
    if 'in billions'  in lower: return 1000.0
    return 1.0


def _infer_scale(raw_revenue: float, ref_revenue_usd: float | None, html: str) -> float | None:
    """Pick the scale factor (raw table units -> millions) that lands closest
    to the ticker's own last known quarterly revenue, instead of trusting a
    document-wide unit label. Returns None if no candidate scale lands within
    3x of the reference — i.e. the extraction is unreliable and should be
    discarded rather than posted."""
    if not ref_revenue_usd:
        return _detect_scale(html)

    ref_millions = ref_revenue_usd / 1e6
    if ref_millions <= 0 or raw_revenue <= 0:
        return _detect_scale(html)

    candidates = (0.001, 1.0, 1000.0)
    best_scale = min(candidates, key=lambda c: abs(math.log(raw_revenue * c / ref_millions)))
    if abs(math.log(raw_revenue * best_scale / ref_millions)) > math.log(3):
        return None
    return best_scale


def fetch_8k_extras(cik: str, accn: str, ref_revenue: float | None = None) -> dict:
    """Parse full quarter financials, EPS, guidance and period end date from
    an earnings 8-K. `ref_revenue` is the ticker's last known quarterly
    revenue in raw USD (from SEC companyfacts) — used to sanity-check the
    scale of numbers scraped from the free-text exhibit table, since the
    exhibit's own unit labels aren't reliable (see _infer_scale)."""
    accn_nodash = accn.replace('-', '')
    cik_int     = str(int(cik))
    try:
        idx_html = _fetch_text(
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{accn}-index.htm"
        )
    except Exception:
        return {}

    exhibit_url = None
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', idx_html, re.S | re.I):
        cells = [re.sub(r'<[^>]+>', '', c).strip()
                 for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S | re.I)]
        if any('EX-99.1' in c for c in cells):
            hrefs = re.findall(r'href="([^"]+\.htm)"', row, re.I)
            if hrefs:
                p = hrefs[0]
                if not p.startswith('http'):
                    p = (f"https://www.sec.gov/Archives/edgar/data"
                         f"/{cik_int}/{accn_nodash}/{p.split('/')[-1]}")
                exhibit_url = p
                break
    if not exhibit_url:
        return {}

    try:
        html = _fetch_text(exhibit_url)
    except Exception:
        return {}

    parser = _TableParser()
    parser.feed(html)
    result = {}
    raw    = {}  # unscaled parsed values, scaled once revenue's magnitude is known

    # ── Label sets ────────────────────────────────────────────────────────────
    eps_labels = {'diluted earnings per share', 'earnings per common share - diluted',
                  'diluted net income per share', 'net income per share - diluted',
                  'diluted eps', 'net income (loss) per share, diluted'}
    rev_labels = {'net revenue', 'total net revenue', 'total revenue',
                  'net revenues', 'total revenues', 'revenues', 'revenue'}
    gp_labels  = {'gross profit', 'gross margin'}
    ni_labels  = {'net income', 'net loss', 'net income (loss)',
                  'net income attributable', 'net loss attributable'}

    def clean(s):
        return re.sub(r'\s+', ' ', s).strip().lower().rstrip(':').strip('*')

    def first_num(row, allow_small=True):
        for c in row[1:]:
            v = re.sub(r'[\s$,]', '', c).replace('(', '-').replace(')', '')
            if re.match(r'^-?\d[\d.]*$', v):
                try:
                    f = float(v)
                    if allow_small or abs(f) >= 1:
                        return f
                except: pass
        return None

    for t in parser.tables:
        for row in t:
            if not row: continue
            label = clean(row[0])
            if 'eps' not in result and label in eps_labels:
                v = first_num(row, allow_small=True)
                if v is not None and abs(v) < 1000:
                    result['eps'] = v
            if 'quarter_revenue' not in raw and label in rev_labels:
                v = first_num(row, allow_small=False)
                if v is not None:
                    raw['quarter_revenue'] = v
            if 'quarter_gross_profit' not in raw and label in gp_labels:
                v = first_num(row, allow_small=False)
                if v is not None:
                    raw['quarter_gross_profit'] = v
            if 'quarter_net_income' not in raw and label in ni_labels:
                v = first_num(row, allow_small=False)
                if v is not None:
                    raw['quarter_net_income'] = v

    if 'quarter_revenue' in raw:
        scale = _infer_scale(raw['quarter_revenue'], ref_revenue, html)
        if scale is not None:
            result['quarter_revenue'] = raw['quarter_revenue'] * scale
            if 'quarter_gross_profit' in raw:
                gp = raw['quarter_gross_profit'] * scale
                if abs(gp) < abs(result['quarter_revenue']) * 1.5:
                    result['quarter_gross_profit'] = gp
            if 'quarter_net_income' in raw:
                result['quarter_net_income'] = raw['quarter_net_income'] * scale

    # ── Quarter period end date from table header ──────────────────────────────
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&#\d+;|&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    # Scan all table cells for the first plausible recent quarter-end date.
    # This avoids regex issues with compound headers like
    # "Fiscal Quarter Ended  Two Fiscal Quarters Ended  May 3, 2026".
    _date_fmts = ('%B %d, %Y', '%B %d,%Y', '%B %d %Y',
                  '%b %d, %Y', '%b. %d, %Y', '%b %d %Y')
    _today = datetime.now(timezone.utc).replace(tzinfo=None)
    for t in parser.tables:
        if 'quarter_end_date' in result:
            break
        for row in t:
            for cell in row:
                raw = re.sub(r'\s+', ' ', cell).strip().rstrip(',')
                if not re.search(r'[A-Za-z]', raw):
                    continue
                for fmt in _date_fmts:
                    try:
                        dt = datetime.strptime(raw, fmt)
                        days_ago = (_today - dt).days
                        if 10 < days_ago < 200:   # plausible recent quarter end
                            result['quarter_end_date'] = dt.strftime('%Y-%m-%d')
                            break
                    except ValueError:
                        pass
                if 'quarter_end_date' in result:
                    break
            if 'quarter_end_date' in result:
                break

    # ── Guidance ──────────────────────────────────────────────────────────────
    m = re.search(
        r'revenue\s+is\s+expected\s+to\s+be\s+\$?([\d,.]+)\s*(billion|million|B|M)',
        text, re.I
    )
    if m:
        val  = float(m.group(1).replace(',', ''))
        unit = m.group(2).lower()
        result['guidance_rev'] = val * (1e9 if unit in ('billion', 'b') else 1e6)

    return result


def find_latest_earnings_8k(cik: str) -> tuple[str | None, str | None]:
    """Return (date, accession_number) of the most recent Item 2.02 8-K, or (None, None)."""
    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                     headers=UA, timeout=15)
    r.raise_for_status()
    recent = r.json().get("filings", {}).get("recent", {})
    for form, date, accn, items in zip(
        recent.get("form", []),
        recent.get("filingDate", []),
        recent.get("accessionNumber", []),
        recent.get("items", [""] * 500),
    ):
        if form == "8-K" and "2.02" in str(items):
            return date, accn
    return None, None


def check_recent_filing(cik: str, days: int = 2) -> str | None:
    """Return filing type if company filed a 10-Q, 10-K, or earnings 8-K within `days` days."""
    r = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers=UA, timeout=15,
    )
    r.raise_for_status()
    recent = r.json().get("filings", {}).get("recent", {})
    forms  = recent.get("form", [])
    dates  = recent.get("filingDate", [])
    items  = recent.get("items", [""] * len(forms))
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)

    for form, date_str, item in zip(forms, dates, items):
        if form not in ("10-Q", "10-K", "8-K"):
            continue
        if form == "8-K" and "2.02" not in str(item):
            continue
        try:
            if datetime.strptime(date_str, "%Y-%m-%d").date() >= cutoff:
                return form
        except ValueError:
            continue
    return None


def fetch_logo(ticker: str) -> None:
    """Download logo from FMP if not already in logos/."""
    logo_dir = ROOT / "logos"
    logo_dir.mkdir(exist_ok=True)
    out = logo_dir / f"{ticker}.png"
    if out.exists():
        return
    try:
        r = requests.get(
            f"https://financialmodelingprep.com/image-stock/{ticker}.png",
            timeout=10,
        )
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            out.write_bytes(r.content)
            print(f"  logo downloaded → logos/{ticker}.png")
        else:
            print(f"  no logo found for {ticker} (HTTP {r.status_code})")
    except Exception as e:
        print(f"  logo download failed: {e}")


def generate_chart(ticker: str, cik: str, company: str, out_path: Path) -> list | None:
    """Fetch EDGAR facts, render chart to out_path. Returns quarters list or None."""
    try:
        fetch_logo(ticker)
        facts    = fetch_facts(cik)
        quarters = build_trend(facts, 8)
        if len(quarters) < 2:
            print(f"  fewer than 2 quarters found — skipping")
            return None
        co_logo = load_logo(ticker)
        br_logo = load_brand_logo()

        _, accn = find_latest_earnings_8k(cik)
        ref_revenue = quarters[-1].get('revenue')
        extras  = fetch_8k_extras(cik, accn, ref_revenue=ref_revenue) if accn else {}

        # Stitch the 8-K quarter into the trend if it isn't in companyfacts yet
        # (common in the 5–40 day window between earnings release and 10-Q filing)
        stitched = False
        qed = extras.get('quarter_end_date')
        if qed and extras.get('quarter_revenue'):
            existing_keys = {q['key'] for q in quarters}
            if qed not in existing_keys:
                # 8-K values are in millions; companyfacts uses raw dollars
                def _to_usd(v): return v * 1e6 if v is not None else None
                new_q = {
                    'end':          datetime.strptime(qed, '%Y-%m-%d'),
                    'key':          qed,
                    'label':        quarter_label(qed),
                    'revenue':      _to_usd(extras['quarter_revenue']),
                    'gross_profit': _to_usd(extras.get('quarter_gross_profit')),
                    'net_income':   _to_usd(extras.get('quarter_net_income')),
                }
                quarters = (quarters + [new_q])[-8:]  # keep latest 8
                stitched = True
                rev_b = extras['quarter_revenue'] / 1e3
                print(f"  8-K quarter stitched: {quarter_label(qed).replace(chr(10),' ')} "
                      f"(rev ${rev_b:.1f}B)")

        # check_recent_filing() only means a filing landed recently — it doesn't
        # mean that filing's numbers are in `quarters` yet. If the 8-K stitch
        # above didn't happen (extraction failed/was rejected as implausible)
        # and companyfacts hasn't synced the new quarter either, quarters[-1]
        # is still last quarter's data. Posting that now, prompted by today's
        # filing, reads as a fresh chart when it's actually stale — and a few
        # hours later, once data syncs, the real new quarter posts too,
        # producing two different charts for the same company in one day.
        days_stale = (datetime.now(timezone.utc).replace(tzinfo=None) - quarters[-1]['end']).days
        if not stitched and days_stale > 100:
            print(f"  recent filing detected but latest usable quarter is still "
                  f"{days_stale}d old — data hasn't synced yet, skipping until next run")
            return None

        # Derive guidance label from the latest quarter end (calendar-consistent)
        if extras.get('guidance_rev'):
            latest_end = quarters[-1]['end']
            next_end   = latest_end + timedelta(days=92)
            extras['guidance_label'] = quarter_label(next_end.strftime("%Y-%m-%d"))

        if extras:
            keys = [k for k in extras
                    if k not in ('guidance_label', 'quarter_end_date',
                                 'quarter_revenue', 'quarter_gross_profit', 'quarter_net_income')]
            if keys:
                print(f"  8-K extras: {', '.join(keys)}")

        fig = build_figure(
            quarters, company, ticker, co_logo, br_logo,
            eps=extras.get('eps'),
            guidance_rev=extras.get('guidance_rev'),
            guidance_label=extras.get('guidance_label'),
        )
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

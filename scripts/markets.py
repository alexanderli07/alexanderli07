#!/usr/bin/env python3
"""Generate a tokyonight-themed "Markets I'm Watching" SVG card.

Fetches ~1 month of daily prices for the S&P 500, NASDAQ, Bitcoin and gold from
Yahoo Finance's public chart API (no key required) and renders a self-contained
SVG with a price, % change and sparkline for each. Run by the "Update Markets
Card" GitHub Action; output is written to dist/markets.svg.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Yahoo Finance symbols. ^GSPC = S&P 500, ^IXIC = NASDAQ Composite,
# BTC-USD = Bitcoin, GC=F = COMEX gold front-month future.
ASSETS = [
    {"sym": "^GSPC",   "name": "S&P 500", "prefix": ""},
    {"sym": "^IXIC",   "name": "NASDAQ",  "prefix": ""},
    {"sym": "BTC-USD", "name": "Bitcoin", "prefix": "$"},
    {"sym": "GC=F",    "name": "Gold",    "prefix": "$"},
]

# --- tokyonight palette (matches the rest of the profile) ---
BG, STROKE, FG, MUTED = "#1a1b27", "#2a2e45", "#c0caf5", "#565f89"
UP, DOWN, FLAT = "#9ece6a", "#f7768e", "#565f89"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"

W, H, P = 840, 200, 18


def fetch(sym):
    """Return {price, series, ok} for a Yahoo symbol, tolerating transient errors."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(sym) + "?range=1mo&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.load(r)
            res = data["chart"]["result"][0]
            price = float(res["meta"]["regularMarketPrice"])
            closes = res["indicators"]["quote"][0]["close"]
            series = [float(c) for c in closes if c is not None]
            if series:
                series[-1] = price          # pin the last point to the live price
            else:
                series = [price]
            return {"price": price, "series": series, "ok": True}
        except Exception as e:                       # noqa: BLE001 - log & retry
            last_err = e
            time.sleep(2 * (attempt + 1))
    print(f"WARN: {sym} failed after retries: {last_err}")
    return {"price": None, "series": [], "ok": False}


def fmt_price(v, prefix):
    return "n/a" if v is None else f"{prefix}{v:,.0f}"


def sparkline(series, sx0, sy_top, sw, sh, col):
    """Return SVG markup for a filled sparkline within the given box."""
    n = len(series)
    mn, mx = min(series), max(series)
    rng = (mx - mn) or 1.0
    pad, sy_bot = 6, sy_top + sh
    pts = [
        (sx0 + sw * (j / (n - 1)),
         sy_top + pad + (1 - (v - mn) / rng) * (sh - 2 * pad))
        for j, v in enumerate(series)
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"M{pts[0][0]:.1f},{sy_bot:.1f} "
            + " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts)
            + f" L{pts[-1][0]:.1f},{sy_bot:.1f} Z")
    return (
        f'<path d="{area}" fill="{col}" fill-opacity="0.12"/>'
        f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.6" fill="{col}"/>'
    )


def build_svg(rows, updated):
    tw = (W - 2 * P) / len(rows)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Market prices over the past month">',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" '
        f'fill="{BG}" stroke="{STROKE}"/>',
        f'<text x="{P}" y="26" font-family="{FONT}" font-size="11" '
        f'letter-spacing="1.5" fill="{MUTED}">MARKETS · PAST MONTH</text>',
        f'<text x="{W - P}" y="26" text-anchor="end" font-family="{FONT}" '
        f'font-size="11" fill="{MUTED}">updated {escape(updated)}</text>',
        f'<line x1="{P}" y1="38" x2="{W - P}" y2="38" stroke="{STROKE}"/>',
    ]
    sy_top, sh = 76, 58
    for i, row in enumerate(rows):
        tx = P + i * tw
        cx = tx + tw / 2
        sx0, sw = tx + 18, tw - 36
        if i:
            out.append(f'<line x1="{tx:.1f}" y1="52" x2="{tx:.1f}" '
                       f'y2="{H - 14}" stroke="{STROKE}"/>')
        out.append(f'<text x="{cx:.1f}" y="64" text-anchor="middle" '
                   f'font-family="{FONT}" font-size="14.5" font-weight="600" '
                   f'fill="{FG}">{escape(row["name"])}</text>')
        series = row["series"]
        if len(series) >= 2:
            up = series[-1] >= series[0]
            col = UP if up else DOWN
            out.append(sparkline(series, sx0, sy_top, sw, sh, col))
            pct = (series[-1] / series[0] - 1) * 100
            label = f'{"▲" if up else "▼"} {abs(pct):.1f}%'
            out.append(f'<text x="{cx:.1f}" y="182" text-anchor="middle" '
                       f'font-family="{FONT}" font-size="12.5" font-weight="600" '
                       f'fill="{col}">{label}</text>')
        else:
            mid = sy_top + sh / 2
            out.append(f'<line x1="{sx0:.1f}" y1="{mid:.1f}" x2="{sx0 + sw:.1f}" '
                       f'y2="{mid:.1f}" stroke="{FLAT}" stroke-dasharray="3 3"/>')
            out.append(f'<text x="{cx:.1f}" y="182" text-anchor="middle" '
                       f'font-family="{FONT}" font-size="12.5" fill="{MUTED}">—</text>')
        out.append(f'<text x="{cx:.1f}" y="162" text-anchor="middle" '
                   f'font-family="{FONT}" font-size="19" font-weight="700" '
                   f'fill="{FG}">{fmt_price(row["price"], row["prefix"])}</text>')
    out.append("</svg>")
    return "".join(out)


def main():
    rows = []
    for a in ASSETS:
        r = fetch(a["sym"])
        r.update(a)
        rows.append(r)
    updated = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    svg = build_svg(rows, updated)
    os.makedirs("dist", exist_ok=True)
    with open(os.path.join("dist", "markets.svg"), "w", encoding="utf-8") as f:
        f.write(svg)
    print("Wrote dist/markets.svg")
    for r in rows:
        print(f"  {r['name']:<8} {fmt_price(r['price'], r['prefix']):>10}  "
              f"({len(r['series'])} pts)")


if __name__ == "__main__":
    main()

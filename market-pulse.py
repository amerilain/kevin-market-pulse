#!/usr/bin/env python3
"""
Market Pulse — All-in-One Crypto CLI
======================================
Zero dependencies. Just Python 3.8+ stdlib.
No API keys needed. 100% self-serviceable.

Usage:
    python3 market-pulse.py                   # Full market overview
    python3 market-pulse.py --briefing-file   # Save full briefing to file
    python3 market-pulse.py --json            # JSON output (pipeable)
    python3 market-pulse.py --watch           # Watch mode (refresh every 60s)
    python3 market-pulse.py --polymarket      # Prediction market top events
    python3 market-pulse.py --regime           # Only regime signal
    python3 market-pulse.py --html             # Generate standalone HTML dashboard
    curl -s https://raw.githubusercontent.com/kevin/market-pulse/main/market-pulse.py | python3

Examples:
    python3 market-pulse.py
    python3 market-pulse.py --watch
    python3 market-pulse.py --json | jq .regime
    python3 market-pulse.py --briefing-file --html

Author: Kevin — Autonomous Business Agent
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Optional

# ── Configuration ────────────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
POLYMARKET_API = "https://gamma-api.polymarket.com"
USER_AGENT = "market-pulse/1.0"
CACHE_TTL = 60  # seconds
MAX_POLY_EVENTS = 10
BRIEFING_DIR = None  # Auto-detect: ./briefings/ or /workspace/briefings/

# ── HTTP Helpers ─────────────────────────────────────────────────────────────


def api_get(url: str, params: dict | None = None, timeout: int = 15) -> Any:
    """Fetch JSON from a URL."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return None


def api_get_many(urls: list[str], timeout: int = 15) -> list[Any]:
    """Fetch multiple URLs (sequential, no dependencies)."""
    return [api_get(u, timeout=timeout) for u in urls]


# ── Data Fetchers ────────────────────────────────────────────────────────────

# Simple in-memory cache to avoid API rate limits from rapid repeated calls
_data_cache = {}

def _cached_fetch(key: str, fetch_fn, ttl: int = 60):
    """Fetch with a simple TTL cache.
    Only caches successful (non-empty) results.
    Empty results are returned but NOT cached, so subsequent calls retry.
    """
    now = time.time()
    if key in _data_cache and now - _data_cache[key]["ts"] < ttl:
        return _data_cache[key]["data"]
    result = fetch_fn()
    # Only cache non-empty results. Empty/failed results drop through.
    if result is not None and result != {} and len(result) > 0:
        _data_cache[key] = {"data": result, "ts": now}
    return result


def get_prices() -> dict:
    """Fetch crypto prices with 24h changes."""
    def _fetch():
        ids = "bitcoin,ethereum,solana,chainlink,avalanche-2,cardano,polkadot,dogecoin,tron,stellar"
        data = api_get(
            f"{COINGECKO_BASE}/simple/price",
            {"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
        )
        if not data:
            return {}

        MAPPING = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "solana": "SOL",
            "chainlink": "LINK",
            "avalanche-2": "AVAX",
            "cardano": "ADA",
            "polkadot": "DOT",
            "dogecoin": "DOGE",
            "tron": "TRX",
            "stellar": "XLM",
        }

        result = {}
        for cg_id, label in MAPPING.items():
            if cg_id in data:
                price = data[cg_id].get("usd", "N/A")
                change = data[cg_id].get("usd_24h_change", 0)
                result[label] = {"price": price, "change_24h": round(change, 2)}
        return result
    return _cached_fetch("prices", _fetch)


def get_fng() -> dict:
    """Fetch Fear & Greed Index."""
    def _fetch():
        data = api_get("https://api.alternative.me/fng/", {"limit": "1"})
        if data and data.get("data"):
            entry = data["data"][0]
            return {
                "value": int(entry["value"]),
                "classification": entry["value_classification"],
                "timestamp": entry["timestamp"],
            }
        return {"value": None, "classification": "Unknown"}
    return _cached_fetch("fng", _fetch, ttl=120)


def get_regime(prices: dict | None = None, fng: dict | None = None) -> dict:
    """Classify market regime from prices + F&G."""
    prices = prices if prices is not None else get_prices()
    fng = fng if fng is not None else get_fng()

    score = 0
    factors = []

    # F&G scoring
    fng_val = fng.get("value", 50)
    if fng_val is not None:
        if fng_val <= 25:
            score += 25
            factors.append(f"F&G {fng_val} — Extreme Fear (+25, contrarian buy)")
        elif fng_val <= 40:
            score += 15
            factors.append(f"F&G {fng_val} — Fear (+15)")
        elif fng_val <= 60:
            score += 0
            factors.append(f"F&G {fng_val} — Neutral")
        elif fng_val <= 75:
            score -= 10
            factors.append(f"F&G {fng_val} — Greed (-10)")
        else:
            score -= 20
            factors.append(f"F&G {fng_val} — Extreme Greed (-20, caution)")

    # BTC change scoring
    btc = prices.get("BTC", {})
    btc_chg = btc.get("change_24h", 0)
    if btc_chg > 10:
        score += 25
        factors.append(f"BTC +{btc_chg:.1f}% → Strong Bullish (+25)")
    elif btc_chg > 5:
        score += 20
        factors.append(f"BTC +{btc_chg:.1f}% → Bullish (+20)")
    elif btc_chg > 2:
        score += 15
        factors.append(f"BTC +{btc_chg:.1f}% → Moderate Bullish (+15)")
    elif btc_chg > 0:
        score += 5
        factors.append(f"BTC +{btc_chg:.1f}% → Slight Bullish (+5)")
    elif btc_chg > -2:
        factors.append(f"BTC {btc_chg:.1f}% → Flat")
    elif btc_chg > -5:
        score -= 10
        factors.append(f"BTC {btc_chg:.1f}% → Slight Bearish (-10)")
    elif btc_chg > -10:
        score -= 20
        factors.append(f"BTC {btc_chg:.1f}% → Bearish (-20)")

    # ETH relative strength (alt season signal)
    eth = prices.get("ETH", {})
    eth_chg = eth.get("change_24h", 0)
    if eth_chg and btc_chg and eth_chg > btc_chg + 3:
        score += 10
        factors.append(f"ETH +{eth_chg:.1f}% outperforming BTC → Alt season (+10)")

    # SOL signal
    sol = prices.get("SOL", {})
    sol_chg = sol.get("change_24h", 0)
    if sol_chg and btc_chg and sol_chg > btc_chg + 3:
        score += 5
        factors.append(f"SOL +{sol_chg:.1f}% outperforming BTC → Rotation (+5)")

    # Classify
    if score >= 60:
        regime, emoji = "BULL", "🟢"
    elif score >= 35:
        regime, emoji = "ACCUMULATE", "🔵"
    elif score >= 15:
        regime, emoji = "SIDEWAYS", "🟡"
    elif score >= -15:
        regime, emoji = "SIDEWAYS", "🟡"
    elif score >= -35:
        regime, emoji = "DISTRIBUTE", "🔴"
    elif score >= -60:
        regime, emoji = "BEAR", "🟣"
    else:
        regime, emoji = "INDETERMINATE", "⚪"

    signal = "LONG / ACCUMULATE" if score > 20 else ("NEUTRAL" if score > -20 else "SHORT / CAUTION")

    return {
        "regime": regime,
        "emoji": emoji,
        "score": score,
        "signal": signal,
        "factors": factors,
        "fng": fng,
    }


def get_top_polymarket_events(limit: int = 10) -> list[dict]:
    """Fetch top prediction market events by volume."""
    data = api_get(
        f"{POLYMARKET_API}/events",
        {
            "closed": "false",
            "limit": str(limit),
            "sort": "volume",
            "order": "desc",
        },
    )
    if not data:
        return []
    events = []
    for e in data:
        title = e.get("title", "Untitled")
        volume = e.get("volume", "0")
        lmsr = e.get("lmsr", {})
        if isinstance(lmsr, dict):
            outcomes = lmsr.get("outcomes", lmsr.get("outcome_prices", [None]))
        else:
            outcomes = [None, None]

        # Get outcomes array from markets
        markets = e.get("markets", [])
        outcome_prices = []
        if markets:
            m = markets[0]
            outcomes_raw = m.get("outcomes", "[]")
            outcome_prices_raw = m.get("outcome_prices", "[]")
            if isinstance(outcomes_raw, str):
                try:
                    outcomes_raw = json.loads(outcomes_raw)
                except (json.JSONDecodeError, TypeError):
                    outcomes_raw = []
            if isinstance(outcome_prices_raw, str):
                try:
                    outcome_prices_raw = json.loads(outcome_prices_raw)
                except (json.JSONDecodeError, TypeError):
                    outcome_prices_raw = []
            outcome_prices = list(zip(outcomes_raw, outcome_prices_raw))
        else:
            outcome_prices = [("Unknown", "0.5")]

        events.append({
            "title": title,
            "volume": format_volume_str(volume),
            "volume_raw": float(volume) if volume else 0,
            "outcomes": outcome_prices,
        })

    events.sort(key=lambda x: x["volume_raw"], reverse=True)
    return events


def format_volume_str(v: Any) -> str:
    """Format a volume number into human-readable string."""
    try:
        v = float(v)
    except (ValueError, TypeError):
        return "$0"
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:.0f}"


# ── Briefing Archive ──────────────────────────────────────────────────────────


def get_briefing_dir() -> str:
    """Get or create the briefing directory."""
    global BRIEFING_DIR
    if BRIEFING_DIR:
        return BRIEFING_DIR
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "briefings"),
        "/workspace/briefings",
        os.path.join(os.getcwd(), "briefings"),
    ]
    for c in candidates:
        try:
            os.makedirs(c, exist_ok=True)
            BRIEFING_DIR = c
            return c
        except (OSError, PermissionError):
            continue
    # Fallback: current dir
    BRIEFING_DIR = "."
    return BRIEFING_DIR


def save_briefing(md: str, filename: str | None = None) -> str:
    """Save a briefing markdown file and return the path."""
    bdir = get_briefing_dir()
    if not filename:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"briefing-{ts}.md"
    path = os.path.join(bdir, filename)
    with open(path, "w") as f:
        f.write(md)
    return path


def load_latest_briefing() -> str | None:
    """Load the most recent briefing file."""
    bdir = get_briefing_dir()
    try:
        files = sorted(
            [f for f in os.listdir(bdir) if f.endswith(".md")],
            reverse=True,
        )
        if files:
            with open(os.path.join(bdir, files[0])) as f:
                return f.read()
    except (OSError, FileNotFoundError):
        pass
    return None


# ── Formatters ────────────────────────────────────────────────────────────────


def format_price_pct(value: float) -> str:
    """Format a percentage with + sign for positive values."""
    if value > 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"


def format_price_usd(price: float) -> str:
    """Format a USD price."""
    if price >= 1000:
        return f"${price:,.0f}"
    if price >= 1:
        return f"${price:,.2f}"
    return f"${price:.4f}"


def build_markdown_overview(prices: dict, regime: dict, polymarket: list[dict] | None = None) -> str:
    """Build a full markdown market overview."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fng = regime["fng"]

    lines = [
        f"# Market Pulse — {now}",
        "",
        f"**Regime**: {regime['emoji']} {regime['regime']} (Score: {regime['score']:+d})",
        f"**Signal**: {regime['signal']}",
        f"**F&G**: {fng.get('value', '?')}/100 — {fng.get('classification', 'Unknown')}",
        "",
        "## Prices (24h Change)",
        "",
        "| Asset | Price | 24h Change |",
        "|-------|-------|------------|",
    ]

    for symbol, data in prices.items():
        price = format_price_usd(data["price"])
        change = format_price_pct(data["change_24h"])
        lines.append(f"| {symbol} | {price} | {change} |")

    lines.extend([
        "",
        "## Regime Factors",
        "",
    ])
    for factor in regime["factors"]:
        lines.append(f"- {factor}")

    if polymarket:
        lines.extend([
            "",
            "## Prediction Markets (Top by Volume)",
            "",
            "| Event | Volume | Top Outcome |",
            "|-------|--------|-------------|",
        ])
        for e in polymarket[:5]:
            outcomes = e.get("outcomes", [("Unknown", "50%")])
            top_outcome = outcomes[0] if outcomes else ("Unknown", "50%")
            # Format outcome price as percentage
            try:
                oprice = float(top_outcome[1]) * 100
                olabel = f"{top_outcome[0]}: {oprice:.1f}%"
            except (ValueError, TypeError, IndexError):
                olabel = "N/A"
            lines.append(f"| {e['title'][:50]} | {e['volume']} | {olabel} |")

    lines.extend([
        "",
        "---",
        f"*Generated by Market Pulse CLI @ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC*",
        "",
    ])
    return "\n".join(lines)


def build_html_dashboard(prices: dict, regime: dict, polymarket: list[dict] | None = None) -> str:
    """Build a standalone HTML dashboard (no external deps)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fng = regime["fng"]
    fng_val = fng.get("value", 50)
    fng_class = fng.get("classification", "Unknown")

    # Build F&G color bar
    fng_color = "#22c55e" if fng_val >= 60 else ("#eab308" if fng_val >= 40 else "#ef4444")

    # Price rows
    price_rows = ""
    for sym, data in prices.items():
        p = format_price_usd(data["price"])
        c = data["change_24h"]
        c_str = format_price_pct(c)
        c_color = "#22c55e" if c > 0 else "#ef4444"
        price_rows += f"""
        <tr>
            <td style="font-weight:bold">{sym}</td>
            <td>{p}</td>
            <td style="color:{c_color}">{c_str}</td>
        </tr>"""

    # Factors
    factors_html = "".join(f"<li>{f}</li>" for f in regime["factors"])

    # Polymarket
    poly_rows = ""
    if polymarket:
        for e in polymarket[:5]:
            outs = e.get("outcomes", [])
            top = outs[0] if outs else ("N/A", "0")
            try:
                op = float(top[1]) * 100
                otxt = f"{top[0]}: {op:.1f}%"
            except (ValueError, TypeError):
                otxt = "N/A"
            poly_rows += f"<tr><td>{e['title'][:45]}</td><td>{e['volume']}</td><td>{otxt}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Pulse</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
.container {{ max-width: 800px; margin: 0 auto; }}
h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
h2 {{ font-size: 1.25rem; margin: 1.5rem 0 0.75rem; color: #94a3b8; }}
.header {{ display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; margin-bottom: 1.5rem; }}
.badge {{ padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.875rem; font-weight: 600; }}
.badge-accumulate {{ background: #1e3a5f; color: #60a5fa; }}
.badge-bull {{ background: #14532d; color: #4ade80; }}
.badge-bear {{ background: #450a0a; color: #f87171; }}
table {{ width: 100%; border-collapse: collapse; margin: 0.75rem 0; }}
th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #1e293b; }}
th {{ color: #64748b; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
.fng-bar {{ height: 0.5rem; border-radius: 999px; background: #1e293b; margin: 0.5rem 0; overflow: hidden; }}
.fng-fill {{ height: 100%; border-radius: 999px; transition: width 1s ease; background: {fng_color}; width: {fng_val}%; }}
ul {{ list-style: none; }}
li {{ padding: 0.375rem 0; border-left: 3px solid #334155; padding-left: 0.75rem; margin: 0.5rem 0; color: #94a3b8; font-size: 0.875rem; }}
.footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #1e293b; color: #475569; font-size: 0.75rem; text-align: center; }}
</style>
</head>
<body>
<div class="container">
    <h1>Market Pulse</h1>
    <div class="header">
        <span class="badge badge-{regime['regime'].lower()}">{regime['emoji']} {regime['regime']}</span>
        <span>Score: {regime['score']:+d}</span>
        <span>Signal: {regime['signal']}</span>
        <span style="color:#64748b;font-size:0.875rem">{now}</span>
    </div>

    <h2>🤑 Fear & Greed: {fng_val}/100 — {fng_class}</h2>
    <div class="fng-bar"><div class="fng-fill"></div></div>

    <h2>💰 Prices</h2>
    <table>
        <tr><th>Asset</th><th>Price</th><th>24h Change</th></tr>
        {price_rows}
    </table>

    <h2>📊 Regime Factors</h2>
    <ul>{factors_html}</ul>

    {f"<h2>🎯 Prediction Markets</h2><table><tr><th>Event</th><th>Volume</th><th>Top Outcome</th></tr>{poly_rows}</table>" if poly_rows else ""}

    <div class="footer">
        Generated by Market Pulse CLI<br>
        {now}
    </div>
</div>
</body>
</html>"""
    return html


def build_json_output(prices: dict, regime: dict, polymarket: list[dict] | None = None) -> dict:
    """Build a JSON-serializable output object."""
    fng = regime["fng"]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": {
            "name": regime["regime"],
            "emoji": regime["emoji"],
            "score": regime["score"],
            "signal": regime["signal"],
            "factors": regime["factors"],
        },
        "fear_greed": {
            "value": fng.get("value"),
            "classification": fng.get("classification"),
        },
        "prices": prices,
        "prediction_markets": [
            {
                "title": e["title"],
                "volume": e["volume"],
                "outcomes": [
                    {"label": o[0], "probability": float(o[1])}
                    for o in e.get("outcomes", [])
                ],
            }
            for e in (polymarket or [])
        ],
    }


# ── Display Functions ────────────────────────────────────────────────────────


def display_full(prices: dict, regime: dict, polymarket: list[dict] | None = None):
    """Display a full formatted market overview to stdout."""
    fng = regime["fng"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("=" * 60)
    print(f"  MARKET PULSE — {now}")
    print("=" * 60)
    print(f"\n  Regime: {regime['emoji']}  {regime['regime']}  (Score: {regime['score']:+d})")
    print(f"  Signal: {regime['signal']}")
    print(f"  F&G:    {fng.get('value', '?')}/100 — {fng.get('classification', 'Unknown')}")
    print()
    print(f"  {'Asset':<8} {'Price':<12} {'24h Change':<12}")
    print(f"  {'─'*8} {'─'*12} {'─'*12}")
    for sym, data in prices.items():
        p = format_price_usd(data["price"])
        c = format_price_pct(data["change_24h"])
        print(f"  {sym:<8} {p:<12} {c:<12}")

    print(f"\n  {'─'*60}")
    print("  REGIME FACTORS")
    for f in regime["factors"]:
        print(f"  • {f}")

    if polymarket:
        print(f"\n  {'─'*60}")
        print(f"  PREDICTION MARKETS (Top by Volume)")
        print(f"  {'─'*60}")
        for i, e in enumerate(polymarket[:5], 1):
            outs = e.get("outcomes", [("N/A", "0")])
            top = outs[0]
            try:
                op = float(top[1]) * 100
                otxt = f"{top[0]}: {op:.1f}%"
            except (ValueError, TypeError):
                otxt = "N/A"
            print(f"  {i}. {e['title'][:55]}")
            print(f"     Vol: {e['volume']:>12}  {otxt}")

    print("\n" + "=" * 60)


def display_regime_only(regime: dict):
    """Display only the regime signal."""
    print(f"{regime['emoji']} {regime['regime']} | Score: {regime['score']:+d} | Signal: {regime['signal']}")


# ── Watch Mode ────────────────────────────────────────────────────────────────


def watch_mode(refresh: int = 60):
    """Continuously refresh market data every N seconds."""
    try:
        while True:
            prices = get_prices()
            regime = get_regime()
            polymarket = get_top_polymarket_events(MAX_POLY_EVENTS)
            os.system("clear" if os.name == "posix" else "cls")
            display_full(prices, regime, polymarket)
            print(f"\n  Auto-refreshing every {refresh}s. Ctrl+C to exit.")
            time.sleep(refresh)
    except KeyboardInterrupt:
        print("\n\n  Market Pulse stopped.")
        sys.exit(0)


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Market Pulse — All-in-One Crypto CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 market-pulse.py                    # Full overview
  python3 market-pulse.py --json             # JSON output
  python3 market-pulse.py --watch            # Live refresh
  python3 market-pulse.py --regime            # Just the regime signal
  python3 market-pulse.py --briefing-file    # Save briefing to file
  python3 market-pulse.py --html --out=dashboard.html  # Export HTML
        """,
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON (pipeable)"
    )
    parser.add_argument(
        "--watch", action="store_true", help="Watch mode (refresh every 60s)"
    )
    parser.add_argument(
        "--refresh", type=int, default=60, help="Refresh interval in seconds (default 60)"
    )
    parser.add_argument(
        "--regime", action="store_true", help="Show only regime signal"
    )
    parser.add_argument(
        "--briefing-file", action="store_true", help="Save briefing markdown to file"
    )
    parser.add_argument(
        "--html", action="store_true", help="Generate HTML dashboard"
    )
    parser.add_argument(
        "--out", type=str, default="market-pulse-dashboard.html",
        help="Output filename for HTML (default: market-pulse-dashboard.html)"
    )
    parser.add_argument(
        "--polymarket", action="store_true", help="Include prediction markets data"
    )

    args = parser.parse_args()

    # Fetch all data (share prices/fng between regime and display to avoid duplicate API calls)
    prices = get_prices()
    fng = get_fng()
    regime = get_regime(prices=prices, fng=fng)
    polymarket = get_top_polymarket_events(MAX_POLY_EVENTS) if (args.polymarket or not args.regime) else None

    # Watch mode
    if args.watch:
        watch_mode(args.refresh)
        return

    # Regime only
    if args.regime:
        display_regime_only(regime)
        return

    # JSON output
    if args.json:
        out = build_json_output(prices, regime, polymarket)
        print(json.dumps(out, indent=2))
        return

    # HTML output
    if args.html:
        html = build_html_dashboard(prices, regime, polymarket)
        out_path = args.out
        with open(out_path, "w") as f:
            f.write(html)
        print(f"✅ HTML dashboard saved to: {out_path}")
        if args.briefing_file:
            md = build_markdown_overview(prices, regime, polymarket)
            path = save_briefing(md)
            print(f"✅ Briefing saved to: {path}")
        return

    # Briefing file
    if args.briefing_file:
        md = build_markdown_overview(prices, regime, polymarket)
        path = save_briefing(md)
        print(f"✅ Briefing saved to: {path}")
        return

    # Default: display full overview
    display_full(prices, regime, polymarket)


if __name__ == "__main__":
    main()

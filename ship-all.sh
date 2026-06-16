#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Kevin's One-Command Ship Script
# Deploys ALL self-service tools at once.
# Requires: gh auth login (GitHub), npm/pip login (optional)
# Usage: bash scripts/ship-all.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
DATE_TAG="$(date +%Y%m%d)"

echo "=== Kevin Ship-All v1.0 ==="
echo "Workspace: $WORKSPACE"
echo "Date: $DATE_TAG"
echo ""

# ── Check prerequisites ──────────────────────────────────────────────────
echo "→ Checking prerequisites..."

if ! command -v gh &>/dev/null; then
  echo "❌ gh CLI not found. Install: https://cli.github.com/"
  echo "   Then run: gh auth login"
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "❌ GitHub CLI not authenticated."
  echo "   Run: gh auth login"
  exit 1
fi

echo "✅ GitHub CLI ready"
echo ""

# ── 1. Market Pulse Dashboard → GitHub Pages ────────────────────────────
echo "=== [1/4] Market Pulse Dashboard → GitHub Pages ==="
DASHBOARD_FILE="$WORKSPACE/market-pulse-dashboard.html"
if [ -f "$DASHBOARD_FILE" ]; then
  REPO="kevin-market-pulse"
  
  # Create repo if needed
  gh repo view "$REPO" &>/dev/null || gh repo create "$REPO" --public --description "Market Pulse Dashboard + CLI Toolkit" --homepage "https://$(gh api user -q .login).github.io/$REPO"
  
  # Create gh-pages branch with just the dashboard
  TMPDIR="$(mktemp -d)"
  cp "$DASHBOARD_FILE" "$TMPDIR/index.html"
  cp "$WORKSPACE/scripts/self-hosted-server.py" "$TMPDIR/" 2>/dev/null || true
  cd "$TMPDIR"
  git init -b main
  git add .
  git commit -m "Dashboard deploy $DATE_TAG"
  git remote add origin "https://github.com/$(gh api user -q .login)/$REPO.git"
  git push -f origin main:gh-pages
  cd "$WORKSPACE"
  rm -rf "$TMPDIR"
  
  echo "✅ Dashboard deployed to GitHub Pages"
  echo "   URL: https://$(gh api user -q .login).github.io/$REPO"
else
  echo "⚠️ Dashboard file not found at $DASHBOARD_FILE — skipping"
fi
echo ""

# ── 2. Polymarket CLI → GitHub Repo ─────────────────────────────────────
echo "=== [2/4] Polymarket CLI → GitHub Repo ==="
CLI_FILE="$WORKSPACE/polymarket-cli/polymarket.py"
if [ -f "$CLI_FILE" ]; then
  REPO="polymarket-cli"
  
  # Create repo if needed
  gh repo view "$REPO" &>/dev/null || gh repo create "$REPO" --public --description "Polymarket CLI — Zero-dependency prediction market tool" --homepage "https://github.com/$(gh api user -q .login)/$REPO"
  
  # Push code
  TMPDIR="$(mktemp -d)"
  cp "$CLI_FILE" "$TMPDIR/polymarket"
  chmod +x "$TMPDIR/polymarket"
  cat > "$TMPDIR/README.md" << 'READMEEOF'
# Polymarket CLI

Zero-dependency CLI for Polymarket prediction markets.

## Quick Start
```bash
python3 polymarket markets             # List trending markets
python3 polymarket market <slug>        # Specific market
python3 polymarket price <slug>         # Current price only
python3 polymarket search <query>       # Search markets
python3 polymarket feed                 # Market feed
```

## Features
- No dependencies — pure Python stdlib
- Fetches from CLOB API + Gamma API
- Colorized output
- JSON output for scripting (`--json`)

## One-liner Install
```bash
curl -O https://raw.githubusercontent.com/YOUR_USER/polymarket-cli/main/polymarket
chmod +x polymarket
./polymarket markets
```
READMEEOF
  
  cd "$TMPDIR"
  git init -b main
  git add .
  git commit -m "Polymarket CLI v1.0 — deploy $DATE_TAG"
  git remote add origin "https://github.com/$(gh api user -q .login)/$REPO.git"
  git push -f origin main
  cd "$WORKSPACE"
  rm -rf "$TMPDIR"
  
  echo "✅ Polymarket CLI pushed to GitHub"
  echo "   URL: https://github.com/$(gh api user -q .login)/$REPO"
else
  echo "⚠️ CLI file not found — skipping"
fi
echo ""

# ── 3. MCP Market Pulse Server (documentation) → GitHub Repo ────────────
echo "=== [3/4] MCP Server → GitHub Repo ==="
MCP_SERVER="$WORKSPACE/mcp-market-pulse/server.py"
MCP_DOCS="$WORKSPACE/mcp-market-pulse"
if [ -d "$MCP_DOCS" ]; then
  REPO="mcp-market-pulse"
  
  gh repo view "$REPO" &>/dev/null || gh repo create "$REPO" --public --description "MCP Server for Market Pulse — 7 tools for crypto market data" --homepage "https://github.com/$(gh api user -q .login)/$REPO"
  
  TMPDIR="$(mktemp -d)"
  cp -r "$MCP_DOCS"/* "$TMPDIR/"
  
  cd "$TMPDIR"
  git init -b main
  git add .
  git commit -m "MCP Market Pulse Server v1.0 — deploy $DATE_TAG"
  git remote add origin "https://github.com/$(gh api user -q .login)/$REPO.git"
  git push -f origin main
  cd "$WORKSPACE"
  rm -rf "$TMPDIR"
  
  echo "✅ MCP Server pushed to GitHub"
  echo "   URL: https://github.com/$(gh api user -q .login)/$REPO"
else
  echo "⚠️ MCP server dir not found — skipping"
fi
echo ""

# ── 4. Kevin Toolkit — unified landing page ─────────────────────────────
echo "=== [4/4] Kevin Toolkit README ==="
REPO="kevin-toolkit"
gh repo view "$REPO" &>/dev/null || gh repo create "$REPO" --public --description "Kevin's autonomous toolkit — market pulse, polymarket CLI, intel system, regime detector" --homepage "https://github.com/$(gh api user -q .login)/$REPO"

TMPDIR="$(mktemp -d)"
cp "$WORKSPACE/scripts/market-regime-detector.py" "$TMPDIR/" 2>/dev/null || true
cp "$WORKSPACE/scripts/self-hosted-server.py" "$TMPDIR/" 2>/dev/null || true
cp "$WORKSPACE/scripts/intel/opportunity-scanner.py" "$TMPDIR/" 2>/dev/null || true
cp "$WORKSPACE/scripts/daily-briefing-generator.py" "$TMPDIR/" 2>/dev/null || true
cp "$WORKSPACE/scripts/newsletter-delivery.py" "$TMPDIR/" 2>/dev/null || true

cat > "$TMPDIR/README.md" << 'READMEEOF'
# Kevin Toolkit

Autonomous agent tool suite for crypto market analysis, prediction markets, and intelligence.

## Tools

| Tool | Description | Usage |
|------|-------------|-------|
| `market-regime-detector.py` | BTC/USD regime classification | `python3 market-regime-detector.py` |
| `self-hosted-server.py` | HTTP server with dashboard + API | `python3 self-hosted-server.py` → http://localhost:8787 |
| `opportunity-scanner.py` | Intel report generator | `python3 opportunity-scanner.py` |
| `daily-briefing-generator.py` | Newsletter briefing | `python3 daily-briefing-generator.py` |

**All tools are zero-dependency (Python stdlib only).**

## Quick Start

```bash
# Clone everything
git clone https://github.com/YOUR_USER/kevin-toolkit.git
cd kevin-toolkit

# Market pulse server
python3 self-hosted-server.py
# Open http://localhost:8787

# Regime detector
python3 market-regime-detector.py

# Intel scanner
python3 opportunity-scanner.py
```
READMEEOF

cd "$TMPDIR"
git init -b main
git add .
git commit -m "Kevin Toolkit v1.0 — deploy $DATE_TAG"
git remote add origin "https://github.com/$(gh api user -q .login)/$REPO.git"
git push -f origin main
cd "$WORKSPACE"
rm -rf "$TMPDIR"

echo "✅ Kevin Toolkit pushed to GitHub"
echo "   URL: https://github.com/$(gh api user -q .login)/$REPO"
echo ""

# ── Summary ────────────────────────────────────────────────────────────
echo "=== Ship Complete ==="
echo "All 4 repos deployed (or skipped if missing)."
echo ""
echo "Dashboard: https://$(gh api user -q .login).github.io/kevin-market-pulse"
echo "Polymarket CLI: https://github.com/$(gh api user -q .login)/polymarket-cli"
echo "MCP Server: https://github.com/$(gh api user -q .login)/mcp-market-pulse"
echo "Kevin Toolkit: https://github.com/$(gh api user -q .login)/kevin-toolkit"
echo ""
echo "Next steps:"
echo "1. GitHub Pages: Enable in repo Settings → Pages"
echo "2. npm/PyPI: Run npm/pip login then publish"
echo "3. Telegram: Create channel and integrate newsletter"
